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

        # 检查LLM类型，适配不同的提示词格式
        llm_type = type(llm).__name__
        self.is_ollama = 'Ollama' in llm_type

        # 创建分析提示词
        self.parser = PydanticOutputParser(pydantic_object=ContentAnalysis)

        if self.is_ollama:
            # Ollama使用简单的字符串提示词
            from langchain.prompts import PromptTemplate
            self.prompt = PromptTemplate.from_template("""你是一个AI和机器人技术领域的专家分析师。

你的任务是分析技术资讯的质量和相关性。

评分标准（0-10分）：
- 信息新鲜度（25%）：是否是最新进展
- 技术深度（20%）：是否有技术相关内容
- 来源权威性（15%）：来源可靠性
- 内容完整性（20%）：信息清晰程度
- 实用价值（20%）：对技术从业者的价值

技术类别：
{categories}

相关性判断原则：
- 只要与AI、机器学习、机器人、大数据、自动化等技术相关，都认为是相关的
- 即使内容简短或不完整，只要主题相关即可
- 优先保证覆盖面而非完美质量

请宽松筛选，确保相关内容不被遗漏。营销内容和完全无关内容才评为不相关。

{format_instructions}

请分析以下资讯：
标题：{title}
内容：{content}
来源：{source}

请给出分类、质量评分和理由。""")
        else:
            # 其他LLM使用ChatPromptTemplate
            self.prompt = ChatPromptTemplate.from_messages([
                ("system", """你是一个AI和机器人技术领域的专家分析师。

你的任务是分析技术资讯的质量和相关性。

评分标准（0-10分）：
- 信息新鲜度（25%）：是否是最新进展
- 技术深度（20%）：是否有技术相关内容
- 来源权威性（15%）：来源可靠性
- 内容完整性（20%）：信息清晰程度
- 实用价值（20%）：对技术从业者的价值

技术类别：
{categories}

相关性判断原则：
- 只要与AI、机器学习、机器人、大数据、自动化等技术相关，都认为是相关的
- 即使内容简短或不完整，只要主题相关即可
- 优先保证覆盖面而非完美质量

请宽松筛选，确保相关内容不被遗漏。营销内容和完全无关内容才评为不相关。

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

        response = chain.invoke({
            "title": item['title'],
            "content": item['content'][:500],  # 限制长度
            "source": item['source'],
            "categories": "\n".join(f"- {cat}" for cat in self.categories),
            "format_instructions": self.parser.get_format_instructions()
        })

        # chain 已经包含解析器，直接返回结果
        return response
