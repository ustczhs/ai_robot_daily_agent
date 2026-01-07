"""
事实检查Agent - 验证新闻真实性和溯源
"""

import logging
from datetime import datetime
from typing import List
from langchain.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from utils.state import NewsItem


class FactCheckResult(BaseModel):
    """事实检查结果"""
    is_real: bool = Field(description="新闻是否真实存在")
    confidence: float = Field(description="置信度(0-1)")
    reason: str = Field(description="判断理由")
    corrected_date: str = Field(description="修正的日期(如果适用)")


class FactCheckerAgent:
    """事实检查Agent"""

    def __init__(self, config: dict, llm):
        self.config = config
        self.llm = llm
        self.logger = logging.getLogger(__name__)

        # 检查LLM类型
        llm_type = type(llm).__name__
        self.is_ollama = 'Ollama' in llm_type

        # 创建事实检查提示词
        self.parser = PydanticOutputParser(pydantic_object=FactCheckResult)

        if self.is_ollama:
            from langchain.prompts import PromptTemplate
            self.prompt = PromptTemplate.from_template("""你是一个专业的事实检查员，擅长验证技术新闻的真实性。

你的任务是检查新闻是否真实存在，特别是避免AI幻觉内容。

检查原则：
1. 验证事件是否在指定日期真实发生
2. 检查来源可靠性
3. 识别明显虚构或夸大内容
4. 重点关注CES展会、ArXiv论文等时效性内容

{format_instructions}

请检查以下新闻：
标题：{title}
内容：{content}
来源：{source}
采集日期：{collected_date}

请给出事实检查结果。""")
        else:
            self.prompt = ChatPromptTemplate.from_messages([
                ("system", """你是一个专业的事实检查员，擅长验证技术新闻的真实性。

你的任务是检查新闻是否真实存在，特别是避免AI幻觉内容。

检查原则：
1. 验证事件是否在指定日期真实发生
2. 检查来源可靠性
3. 识别明显虚构或夸大内容
4. 重点关注CES展会、ArXiv论文等时效性内容

{format_instructions}"""),
                ("user", """请检查以下新闻：

标题：{title}
内容：{content}
来源：{source}
采集日期：{collected_date}

请给出事实检查结果。""")
            ])

    def check_facts(self, items: List[NewsItem]) -> List[NewsItem]:
        """检查所有条目的真实性"""
        checked_items = []

        for i, item in enumerate(items):
            try:
                self.logger.info(f"   事实检查 {i+1}/{len(items)}: {item['title'][:50]}...")

                # 调用LLM检查
                check_result = self._check_item(item)

                # 根据检查结果决定是否保留
                if check_result.is_real and check_result.confidence > 0.7:
                    # 保留真实新闻
                    checked_items.append(item)
                    self.logger.debug(f"      ✓ 真实 (置信度: {check_result.confidence:.2f})")
                else:
                    self.logger.debug(f"      ✗ 疑似虚假 (置信度: {check_result.confidence:.2f}) - {check_result.reason}")

            except Exception as e:
                self.logger.warning(f"   事实检查失败: {str(e)}")
                # 检查失败时保守处理，保留新闻但降低质量分数
                current_score = item.get('quality_score')
                if current_score is not None:
                    item['quality_score'] = current_score * 0.8
                else:
                    item['quality_score'] = 4.0  # 默认降低分数
                checked_items.append(item)
                continue

        return checked_items

    def _check_item(self, item: NewsItem) -> FactCheckResult:
        """检查单个条目"""
        chain = self.prompt | self.llm | self.parser

        collected_date = item.get('published_date', datetime.now()).strftime('%Y-%m-%d')

        response = chain.invoke({
            "title": item['title'],
            "content": item['content'][:300],  # 限制长度
            "source": item.get('source', 'Unknown'),
            "collected_date": collected_date,
            "format_instructions": self.parser.get_format_instructions()
        })

        return response
