"""
内容分析Agent - 分析内容质量、分类、评分
"""

import logging
from typing import List
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from utils.state import NewsItem


class ContentAnalysis(BaseModel):
    """内容分析结果"""
    category: str = Field(description="技术类别")
    quality_score: float = Field(description="质量分数(0-10)")
    is_relevant: bool = Field(description="是否相关")
    reason: str = Field(description="评分理由")


class AnalyzerAgent:
    """内容分析Agent"""
    
    def __init__(self, config: dict, llm):
        self.config = config
        self.llm = llm
        self.logger = logging.getLogger(__name__)
        self.min_quality_score = config['filtering']['min_quality_score']
        self.categories = config['categories']
        
        # 创建分析提示词
        self.parser = PydanticOutputParser(pydantic_object=ContentAnalysis)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个AI和机器人技术领域的专家分析师。

你的任务是分析技术资讯的质量和相关性。

评分标准（0-10分）：
- 信息新鲜度（30%）：是否是最新突破或进展
- 技术深度（25%）：是否有技术细节和实质内容
- 来源权威性（20%）：来源是否可靠
- 内容完整性（15%）：信息是否完整清晰
- 实用价值（10%）：是否对从业者有参考价值

技术类别：
{categories}

请严格筛选，宁缺毋滥。过时的技术、营销软文、重复内容应给低分。

{format_instructions}"""),
            ("user", """请分析以下资讯：

标题：{title}
内容：{content}
来源：{source}

请给出分类、质量评分和理由。""")
        ])
    
    def analyze(self, items: List[NewsItem]) -> List[NewsItem]:
        """分析所有条目"""
        analyzed_items = []
        
        for i, item in enumerate(items):
            try:
                self.logger.info(f"   分析 {i+1}/{len(items)}: {item['title'][:50]}...")
                
                # 调用LLM分析
                analysis = self._analyze_item(item)
                
                # 更新条目信息
                item['category'] = analysis.category
                item['quality_score'] = analysis.quality_score
                
                # 只保留高质量内容
                if analysis.is_relevant and analysis.quality_score >= self.min_quality_score:
                    analyzed_items.append(item)
                    self.logger.debug(f"      ✓ 评分: {analysis.quality_score:.1f} - {analysis.reason}")
                else:
                    self.logger.debug(f"      ✗ 评分: {analysis.quality_score:.1f} - 已过滤")
                
            except Exception as e:
                self.logger.warning(f"   分析失败: {str(e)}")
                continue
        
        return analyzed_items
    
    def _analyze_item(self, item: NewsItem) -> ContentAnalysis:
        """分析单个条目"""
        chain = self.prompt | self.llm | self.parser
        
        result = chain.invoke({
            "title": item['title'],
            "content": item['content'][:500],  # 限制长度
            "source": item['source'],
            "categories": "\n".join(f"- {cat}" for cat in self.categories),
            "format_instructions": self.parser.get_format_instructions()
        })
        
        return result
