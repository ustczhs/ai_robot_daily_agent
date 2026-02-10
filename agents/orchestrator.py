"""
Agent编排器 - 协调各个Agent完成日报生成
"""
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_ollama import OllamaLLM
from langgraph.graph import StateGraph, END

from agents.collector import CollectorAgent
from agents.analyzer import AnalyzerAgent
from agents.deduplicator import DeduplicatorAgent
from agents.reporter import ReporterAgent
from agents.fact_checker import FactCheckerAgent
from utils.state import AgentState


class DailyReportOrchestrator:
    """日报生成编排器"""
    
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 根据配置初始化LLM
        provider = config['llm']['provider'].lower()

        if provider == 'ollama':
            # 使用本地Ollama模型
            self.llm = OllamaLLM(
                model=config['llm']['model'],
                base_url=config['llm'].get('ollama_base_url', 'http://localhost:11434'),
                temperature=config['llm']['temperature']
            )
            self.logger.info(f"使用本地Ollama模型: {config['llm']['model']}")

        elif provider in ['dashscope', 'openai']:
            # 使用远程API
            self.llm = ChatOpenAI(
                model=config['llm']['model'],
                temperature=config['llm']['temperature'],
                max_tokens=config['llm']['max_tokens'],
                openai_api_base=config['llm'].get('base_url'),
                openai_api_key=os.getenv('DASHSCOPE_API_KEY') or os.getenv('OPENAI_API_KEY')
            )
            self.logger.info(f"使用远程API模型: {config['llm']['model']} ({provider})")

        else:
            raise ValueError(f"不支持的LLM提供商: {provider}。支持: dashscope, openai, ollama")
        
        # 初始化嵌入模型
        self.embeddings = OpenAIEmbeddings(
            model=config['embedding']['model'],
            openai_api_base=config['embedding'].get('base_url'),
            openai_api_key=os.getenv('DASHSCOPE_API_KEY') or os.getenv('OPENAI_API_KEY')
        )
        
        # 初始化各个Agent
        self.collector = CollectorAgent(config, self.llm)
        self.fact_checker = FactCheckerAgent(config, self.llm)
        self.analyzer = AnalyzerAgent(config, self.llm)
        self.deduplicator = DeduplicatorAgent(config, self.embeddings)
        self.reporter = ReporterAgent(config, self.llm)
        
        # 构建工作流
        self.workflow = self._build_workflow()
    
    def _build_workflow(self) -> StateGraph:
        """构建Agent工作流"""
        workflow = StateGraph(AgentState)

        # 添加节点
        workflow.add_node("collect", self._collect_node)
        # workflow.add_node("fact_check", self._fact_check_node)  # 暂时禁用
        workflow.add_node("analyze", self._analyze_node)
        workflow.add_node("deduplicate", self._deduplicate_node)
        workflow.add_node("report", self._report_node)

        # 定义流程：collect -> analyze -> deduplicate -> report (暂时跳过fact_check)
        workflow.set_entry_point("collect")
        workflow.add_edge("collect", "analyze")
        workflow.add_edge("analyze", "deduplicate")
        workflow.add_edge("deduplicate", "report")
        workflow.add_edge("report", END)

        return workflow.compile()
    
    def _collect_node(self, state: AgentState) -> AgentState:
        """信息采集节点"""
        self.logger.info("📡 阶段1: 信息采集")
        raw_items = self.collector.collect()
        state['raw_items'] = raw_items
        state['stage'] = 'collected'
        self.logger.info(f"   收集到 {len(raw_items)} 条原始信息")
        return state

    def _fact_check_node(self, state: AgentState) -> AgentState:
        """事实检查节点"""
        self.logger.info("✅ 阶段2: 事实检查与验证")
        checked_items = self.fact_checker.check_facts(state['raw_items'])
        state['checked_items'] = checked_items
        state['stage'] = 'fact_checked'
        self.logger.info(f"   事实检查完成，保留 {len(checked_items)} 条真实内容")
        return state

    def _analyze_node(self, state: AgentState) -> AgentState:
        """内容分析节点"""
        self.logger.info("🔍 阶段2: 内容分析与评分")
        analyzed_items = self.analyzer.analyze(state['raw_items'])
        state['analyzed_items'] = analyzed_items
        state['stage'] = 'analyzed'
        self.logger.info(f"   分析完成，保留 {len(analyzed_items)} 条高质量内容")
        return state
    
    def _deduplicate_node(self, state: AgentState) -> AgentState:
        """去重节点"""
        self.logger.info("🔄 阶段3: 语义去重")
        unique_items = self.deduplicator.deduplicate(state['analyzed_items'])
        state['unique_items'] = unique_items
        state['stage'] = 'deduplicated'
        self.logger.info(f"   去重完成，剩余 {len(unique_items)} 条独特内容")
        return state

    def _report_node(self, state: AgentState) -> AgentState:
        """报告生成节点"""
        self.logger.info("📝 阶段4: 生成报告")
        report_path = self.reporter.generate_report(state['unique_items'])
        state['report_path'] = report_path
        state['stage'] = 'completed'
        self.logger.info(f"   报告已生成: {report_path}")
        return state
    
    def run(self) -> tuple[str, int]:
        """运行完整流程
        
        Returns:
            tuple: (报告路径, 资讯数量)
        """
        # 初始化状态
        initial_state = AgentState(
            raw_items=[],
            checked_items=[],
            analyzed_items=[],
            unique_items=[],
            stage='initialized',
            report_path='',
            timestamp=datetime.now()
        )

        # 执行工作流
        final_state = self.workflow.invoke(initial_state)

        # 返回报告路径和资讯数量
        items_count = len(final_state['unique_items'])
        return final_state['report_path'], items_count