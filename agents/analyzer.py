"""
内容分析Agent - 分析内容质量、分类、评分
"""

import logging
from datetime import datetime, timedelta
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

        # 初始化智能过滤参数
        self.tech_keywords = [
            # 机器人核心技术
            '机器人', 'robot', '无人机', 'drone', '机械臂', 'manipulator', 'cobots',
            '四足', 'quadruped', '人形', 'humanoid', '双足', 'bipedal', 'AGV', '智能车',

            # AI和算法
            'AI', '人工智能', '机器学习', '深度学习', '神经网络', 'reinforcement learning',
            'SLAM', '路径规划', '运动控制', 'computer vision', '图像识别',

            # 硬件和技术参数
            '传感器', 'sensor', '控制器', 'controller', '伺服电机', '伺服', 'DOF', '自由度',
            'payload', '载重', 'battery', '电池', '续航', '芯片', 'processor', 'GPU', 'TPU',

            # 技术规格
            '精度', 'accuracy', '速度', 'velocity', '力矩', 'torque', '刚度', 'stiffness',
            '算法', 'algorithm', '模型', 'model', '框架', 'framework',

            # 应用场景
            '工业', 'industrial', '医疗', 'medical', '服务', 'service', '家庭', 'home',
            '物流', 'logistics', '安防', 'security', '教育', 'education'

            # 3D技术
            '3D', '三维', '三维视频', '3D视频', '3D视频通话', '3D video call', 'AI OS', 'AI操作系统'
        ]

        # 负面关键词 - 这些关键词出现时降低评分
        self.negative_keywords = [
            '财经', '股票', '股市', 
            '娱乐', '明星', '综艺', '电影', '电视剧', '音乐', '游戏',
            '体育', '足球', '篮球', '比赛', '冠军',
            '政治', '政府', '政策', '法规', '会议',
            '天气', '交通', '事故', '犯罪', '社会新闻'
        ]

        # 来源质量评分
        self.source_quality = {
            '36氪': 1.0, '雷科技': 1.0, '机器之心': 1.0, '新智元': 1.0,
            'DeepTech': 1.0, 'MIT Technology Review': 1.0, 'IEEE': 1.0,
            'Nature': 1.0, 'Science': 1.0, 'arXiv': 1.0,
            '腾讯新闻': 0.8, '新浪财经': 0.8, '新华网': 0.8,
            '人民网': 0.7, '中新网': 0.7, '中国新闻网': 0.7,
            '中华网': 0.6, '同花顺财经': 0.5, '第一财经': 0.7
        }

        # 过滤阈值
        self.pre_filter_threshold = 0.3  # 预过滤阈值，0-1之间
        self.min_content_length = 100   # 最小内容长度

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

        # 获取配置中的最大年龄限制
        max_age_hours = self.config['filtering']['max_age_hours']
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

        # 标题去重集合，避免标题完全相同的新闻
        seen_titles = set()

        self.logger.info(f"   使用日期过滤: 保留{max_age_hours}小时内的新闻 (截止时间: {cutoff_time})")
        self.logger.info(f"   使用标题去重: 过滤标题完全相同的新闻")

        for i, item in enumerate(items):
            try:
                self.logger.info(f"   分析 {i+1}/{len(items)}: {item['title'][:50]}...")

                # 首先检查标题是否重复（增强版去重）
                title_normalized = self._normalize_title_for_deduplication(item['title'])
                if title_normalized in seen_titles:
                    self.logger.debug(f"      ✗ 标题重复，已过滤: {item['title']}")
                    continue

                # 其次检查日期是否在允许范围内
                if item.get('published_date') and isinstance(item['published_date'], datetime):
                    if item['published_date'] < cutoff_time:
                        self.logger.debug(f"      ✗ 过期新闻，已过滤 (发布日期: {item['published_date']})")
                        continue
                    else:
                        self.logger.debug(f"      ✓ 日期有效: {item['published_date']}")
                else:
                    # 如果没有发布日期，直接过滤掉（不再允许无日期新闻通过）
                    self.logger.debug(f"      ✗ 无发布日期，已过滤")
                    continue

                # 第三步：智能预过滤 - 检查技术相关性
                pre_filter_score = self._calculate_pre_filter_score(item)
                if pre_filter_score < self.pre_filter_threshold:
                    self.logger.debug(f"      ✗ 预过滤不通过 (分数: {pre_filter_score:.2f})")
                    continue
                else:
                    self.logger.debug(f"      ✓ 预过滤通过 (分数: {pre_filter_score:.2f})")

                # 调用LLM分析
                analysis = self._analyze_item(item)

                # 更新条目信息
                item['category'] = analysis.category
                item['quality_score'] = analysis.quality_score

                # 只保留高质量内容
                if analysis.is_relevant and analysis.quality_score >= self.min_quality_score:
                    analyzed_items.append(item)
                    seen_titles.add(title_normalized)  # 添加到已见标题集合
                    self.logger.debug(f"      ✓ 评分: {analysis.quality_score:.1f} - {analysis.reason}")
                else:
                    self.logger.debug(f"      ✗ 评分: {analysis.quality_score:.1f} - 已过滤")

            except Exception as e:
                self.logger.warning(f"   分析失败: {str(e)}")
                continue

        self.logger.info(f"   分析完成: 从 {len(items)} 条新闻中保留 {len(analyzed_items)} 条高质量内容")
        return analyzed_items
    
    def _analyze_item(self, item: NewsItem) -> ContentAnalysis:
        """分析单个条目"""
        chain = self.prompt | self.llm | self.parser

        # 优先使用完整网页内容，如果没有则使用摘要
        content_to_analyze = item.get('full_content')
        if not content_to_analyze or len(content_to_analyze.strip()) < 50:
            # 回退到原有content字段
            content_to_analyze = item.get('content', '')
            self.logger.debug(f"使用摘要内容进行分析: {len(content_to_analyze)} 字符")
        else:
            self.logger.debug(f"使用完整网页内容进行分析: {len(content_to_analyze)} 字符")

        response = chain.invoke({
            "title": item['title'],
            "content": content_to_analyze[:1000],  # 增加长度限制，因为现在有完整内容
            "source": item['source'],
            "categories": "\n".join(f"- {cat}" for cat in self.categories),
            "format_instructions": self.parser.get_format_instructions()
        })

        # chain 已经包含解析器，直接返回结果
        return response

    def _normalize_title_for_deduplication(self, title: str) -> str:
        """为去重目的标准化标题"""
        if not title:
            return ""

        import re

        # 转换为小写
        normalized = title.lower().strip()

        # 移除常见的来源后缀
        source_suffixes = [
            r'[-—]\s*腾讯新闻$', r'[-—]\s*新浪财经$', r'[-—]\s*新浪网$',
            r'[-—]\s*新华网$', r'[-—]\s*人民网$', r'[-—]\s*中新网$',
            r'[-—]\s*中国新闻网$', r'[-—]\s*中华网$', r'[-—]\s*36氪$',
            r'[-—]\s*雷科技$', r'[-—]\s*凤凰网$', r'[-—]\s*搜狐$',
            r'[-—]\s*同花顺财经$', r'[-—]\s*无忧资讯$', r'[-—]\s*第一财经$',
            r'[-—]\s*界面新闻$', r'[-—]\s*每日经济新闻$', r'[-—]\s*每日经济新闻评论$',
            r'[-—]\s*每经热评$', r'[-—]\s*长株潭.*$', r'[-—]\s*长沙晚报$',
            r'[-—]\s*投中网$', r'[-—]\s*财联社$', r'[-—]\s*ThePaper\.cn$',
            r'[-—]\s*QQ\s*News$', r'[-—]\s*ZDNET$', r'[-—]\s*Trend\s*Hunter$',
            r'[-—]\s*뉴\s*스\s*메\s*카$',  # 韩文来源
            r'\|.*$',  # 移除 | 之后的内容
            r'·.*$',   # 移除 · 之后的内容
        ]

        for suffix_pattern in source_suffixes:
            normalized = re.sub(suffix_pattern, '', normalized, flags=re.IGNORECASE)

        # 移除括号内容（包括中英文括号）
        normalized = re.sub(r'\([^)]*\)', '', normalized)  # 英文括号
        normalized = re.sub(r'（[^）]*）', '', normalized)  # 中文括号
        normalized = re.sub(r'\[[^\]]*\]', '', normalized)  # 方括号

        # 移除多余的标点和空格
        normalized = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', normalized)  # 保留中文和英文字符及空格

        # 移除多余空格
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized

    def _calculate_pre_filter_score(self, item: NewsItem) -> float:
        """计算预过滤分数 (0-1之间)"""
        score = 0.0
        factors = []

        # 获取要分析的文本内容
        title_text = item['title'].lower()
        content_text = ""
        if item.get('full_content') and len(item['full_content'].strip()) > 50:
            content_text = item['full_content'][:2000].lower()  # 限制长度
        elif item.get('content'):
            content_text = item['content'][:1000].lower()

        combined_text = f"{title_text} {content_text}"

        # 1. 技术关键词密度 (40%权重)
        tech_density = self._calculate_tech_density(combined_text)
        score += tech_density * 0.4
        factors.append(f"技术密度:{tech_density:.2f}")

        # 2. 负面关键词检查 (30%权重)
        negative_penalty = self._calculate_negative_penalty(combined_text)
        score += (1.0 - negative_penalty) * 0.3
        factors.append(f"负面惩罚:{negative_penalty:.2f}")

        # 3. 内容长度检查 (15%权重)
        content_length = len(combined_text.strip())
        if content_length >= self.min_content_length:
            length_score = min(1.0, content_length / 1000.0)  # 标准化到0-1
        else:
            length_score = max(0.0, content_length / self.min_content_length)
        score += length_score * 0.15
        factors.append(f"内容长度:{length_score:.2f}")

        # 4. 来源质量 (15%权重)
        source_score = self.source_quality.get(item['source'], 0.5)  # 默认中等质量
        score += source_score * 0.15
        factors.append(f"来源质量:{source_score:.2f}")

        # 确保分数在0-1范围内
        final_score = max(0.0, min(1.0, score))

        self.logger.debug(f"预过滤详情 - 标题: {item['title'][:30]}... | 分数: {final_score:.2f} | 因素: {' | '.join(factors)}")

        return final_score

    def _calculate_tech_density(self, text: str) -> float:
        """计算技术关键词密度"""
        if not text:
            return 0.0

        words = text.split()
        if not words:
            return 0.0

        tech_count = 0
        for word in words:
            # 检查每个词是否包含技术关键词
            for keyword in self.tech_keywords:
                if keyword.lower() in word:
                    tech_count += 1
                    break  # 每个词只计数一次

        density = tech_count / len(words)

        # 标准化到0-1范围，适当放大以提高区分度
        normalized_density = min(1.0, density * 3.0)

        return normalized_density

    def _calculate_negative_penalty(self, text: str) -> float:
        """计算负面关键词惩罚分数"""
        if not text:
            return 0.0

        penalty = 0.0
        words = text.split()

        for word in words:
            for negative_keyword in self.negative_keywords:
                if negative_keyword.lower() in word:
                    penalty += 0.1  # 每个负面关键词增加0.1惩罚
                    break

        # 限制惩罚最大值为1.0
        return min(1.0, penalty)
