"""
报告生成Agent - 生成结构化的技术日报
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict
from collections import defaultdict
from langchain.prompts import ChatPromptTemplate

from utils.state import NewsItem


class ReporterAgent:
    """报告生成Agent"""

    def __init__(self, config: dict, llm):
        self.config = config
        self.llm = llm
        self.logger = logging.getLogger(__name__)
        self.output_dir = Path(config['report']['output_dir'])
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 检查LLM类型，适配不同的提示词格式
        llm_type = type(llm).__name__
        self.is_ollama = 'Ollama' in llm_type
        
    def generate_report(self, items: List[NewsItem]) -> str:
        """生成报告"""
        # 按类别分组
        categorized = self._categorize_items(items)
        
        # 生成报告内容
        report_content = self._build_report(categorized, items)
        
        # 保存报告
        report_path = self._save_report(report_content)
        
        return str(report_path)
    
    def _categorize_items(self, items: List[NewsItem]) -> Dict[str, List[NewsItem]]:
        """按类别分组"""
        categorized = defaultdict(list)
        
        for item in items:
            category = item.get('category', '其他')
            categorized[category].append(item)
        
        # 按质量分数排序
        for category in categorized:
            categorized[category].sort(
                key=lambda x: x.get('quality_score', 0),
                reverse=True
            )
        
        return dict(categorized)
    
    def _build_report(self, categorized: Dict[str, List[NewsItem]], all_items: List[NewsItem]) -> str:
        """构建报告内容"""
        today = datetime.now().strftime('%Y年%m月%d日')
        
        # 报告头部
        report = f"""# 🤖 AI与机器人技术日报

**日期**: {today}  
**生成时间**: {datetime.now().strftime('%H:%M:%S')}

---

## 📊 今日概览

- **收集资讯**: {len(all_items)} 条
- **技术类别**: {len(categorized)} 个
- **信息来源**: {len(set(item['source'] for item in all_items))} 个

---

## 🔥 技术分类

"""
        
        # 按类别生成内容
        max_items = self.config['report']['max_items_per_category']
        
        for category, items in categorized.items():
            report += f"\n### {category}\n\n"
            
            for i, item in enumerate(items[:max_items], 1):
                # 生成幽默点评
                comment = self._generate_comment(item)
                # 打印输出item的全部context内容以供调试
                self.logger.info(f"生成点评 - content: {item['content']}...") 
                self.logger.info(f"生成点评 - full_content: {item['full_content']}...")  
                report += f"{i}. **[{item['title']}]({item['url']})**\n"
                report += f"   - 📰 来源: {item['source']}\n"

                # 添加发布时间显示
                published_date = item.get('published_date')
                if published_date and isinstance(published_date, datetime):
                    # 格式化为中文时间格式
                    time_str = published_date.strftime('%Y年%m月%d日')
                    report += f"   - 🕒 发布时间: {time_str}\n"
                else:
                    report += f"   - 🕒 发布时间: 未知\n"

                report += f"   - ⭐ 评分: {item.get('quality_score', 0):.1f}/10\n"
                report += f"   - 💬 简介: {comment}\n\n"
        
        # 生成分析部分
        if self.config['report']['include_trend_analysis']:
            report += "\n---\n\n"
            report += self._generate_trend_analysis(all_items)
        
        if self.config['report']['include_insights']:
            report += "\n---\n\n"
            report += self._generate_insights(all_items)
        
        if self.config['report']['include_predictions']:
            report += "\n---\n\n"
            report += self._generate_predictions(all_items)
        
        # 报告尾部
        report += f"\n---\n\n*本报告由AI自动生成 | 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"
        
        return report
    
    def _generate_comment(self, item: NewsItem) -> str:
        """生成详细点评和内容介绍"""
        if self.is_ollama:
            # Ollama使用简单的字符串提示词
            from langchain.prompts import PromptTemplate         
            prompt = PromptTemplate.from_template("""你是一个严格事实导向的技术内容分析师，只基于提供的标题、内容和来源生成简短的中文点评。绝不添加任何未在输入中明确出现的信息。

严格要求：
1. 用1-2句话准确概括输入内容中的核心产品、技术或创新点（必须直接引用或紧密改述原文关键点，无细节时简述发布事实）
2. 分析这项技术的实际意义和应用前景（2-3句话，只讨论原文中明确提及的场景或影响，使用定性描述，避免量化）
3. 总长度控制在100-150字，用简体中文输出，关键字可以用英文表示
4. 严禁提及任何数字、百分比或量化指标，除非原文中明确出现并引用来源

示例（仅供结构参考）：
"Lenovo预览了Lenovo Qira个人AI代理，支持跨设备上下文连续性，帮助用户在PC、平板和手机间无缝切换任务。该技术强调隐私优先的混合AI架构，在企业混合办公场景中提供更自然的交互体验。预计将推动多设备生态的智能协同发展。"

严禁：
1. 捏造任何数据、数字、百分比、性能指标、技术细节或产品名称
2. 长篇大论
3. 使用未在原文出现的量化语言（如“提升XX%”）
4. 输出与输入无关的内容
5. 全英文输出                                                  

标题：{title}
内容：{content}
来源：{source}

请生成技术点评：""")
        else:
            # 其他LLM使用ChatPromptTemplate
            prompt = PromptTemplate.from_template("""你是一个严格事实导向的技术内容分析师，只基于提供的标题、内容和来源生成中文点评。绝不添加任何未在输入中明确出现的信息。来源（如StoryHub）仅作为发布平台，不要误解为产品或技术。

严格要求：
1. 先用1-2句话准确概括输入内容中的核心产品、技术或创新点（必须直接引用或紧密改述原文关键点，无细节时简述发布事实）
2. 分析这项技术的实际意义和应用前景（2-3句话，只讨论原文中明确提及的场景或影响，使用定性描述，避免量化）
3. 保持专业性，突出技术价值
4. 总长度控制在100-150字，用简体中文输出，关键字可以用英文表示
5. 严禁提及任何数字、百分比或量化指标，除非原文中明确出现并引用来源
6. 所有内容必须100%基于提供的{title}、{content}和{source}，如技术细节或性能数据不足，则使用定性语言（如“提升效率”“改善体验”）描述，避免具体数字
7. 如原文仅为企业新闻发布，无深层量化细节，只描述主要特性与潜在应用

示例（仅供结构参考）：
"Lenovo预览了Lenovo Qira个人AI代理，支持跨设备上下文连续性，帮助用户在PC、平板和手机间无缝切换任务。该技术强调隐私优先的混合AI架构，在企业混合办公场景中提供更自然的交互体验。预计将推动多设备生态的智能协同发展。"

严禁：
1. 捏造任何数据、数字、百分比、性能指标、技术细节或产品名称
2. 将新闻来源平台误解为技术产品
3. 引入输入中未提及的技术细节
4. 使用未在原文出现的量化语言（如“提升XX%”）
5. 输出与输入无关的内容
6. 全英文输出                                                  

标题：{title}
内容：{content}
来源：{source}

请生成技术点评：""")

        try:
            chain = prompt | self.llm
            response = chain.invoke({
                "title": item['title'],
                "content": item['full_content'],
                "source": item.get('source', 'Unknown')
            })

            # 调试信息
            self.logger.debug(f"LLM点评响应类型: {type(response)}")
            self.logger.debug(f"LLM点评响应内容: {response}")

            # 处理ollama和openai的不同响应格式
            if self.is_ollama:
                # Ollama返回字符串
                if isinstance(response, str):
                    content = response.strip()
                elif hasattr(response, 'content') and response.content:
                    content = response.content.strip()
                else:
                    content = str(response).strip()
            else:
                # OpenAI返回对象
                if hasattr(response, 'content') and response.content:
                    content = response.content.strip()
                else:
                    content = ""

            if content:
                return content
            else:
                self.logger.warning("LLM返回内容为空")
                return "值得关注的技术进展"

        except Exception as e:
            self.logger.error(f"生成点评失败: {str(e)}")
            return "值得关注的技术进展"
    
    def _generate_trend_analysis(self, items: List[NewsItem]) -> str:
        """生成趋势分析"""
        if self.is_ollama:
            from langchain.prompts import PromptTemplate
            prompt = PromptTemplate.from_template("""你是一个技术趋势分析专家。只基于今日提供的资讯标题和类别分布，提炼3个核心趋势。

要求：
1. 严格从标题中提取热点（如具身智能、家庭机器人、中国出海等），避免外部知识
2. 每个趋势2-3句：先描述现象（引用相关标题），再分析原因/影响
3. 专业易懂，无推测性语言
4. 输出格式：
**趋势1: [标题]**
描述...

今日资讯标题：
{titles}

类别分布：
{categories}

请输出3个趋势：""")
        else:
            prompt = PromptTemplate.from_template("""你是一个技术趋势分析专家。只基于今日提供的资讯标题和类别分布，提炼3个核心趋势。

要求：
1. 严格从标题中提取热点（如具身智能、家庭机器人、中国出海等），避免外部知识
2. 每个趋势2-3句：先描述现象（引用1-2条标题），再分析原因/影响
3. 专业易懂，无推测性语言
4. 输出格式：
**趋势1: [标题]**
描述...

今日资讯标题（前20条）：
{titles}

类别分布：
{categories}

请输出3个趋势：""")

        try:
            # 使用所有已分析条目，而不是只用前20条
            titles = "\n".join(f"- {item['title']}" for item in items)

            # 统计类别分布
            category_count = defaultdict(int)
            for item in items:
                category = item.get('category', '其他')
                category_count[category] += 1

            categories = "\n".join(
                f"- {cat}: {count}条"
                for cat, count in sorted(category_count.items(), key=lambda x: x[1], reverse=True)
            )

            chain = prompt | self.llm
            response = chain.invoke({"titles": titles, "categories": categories})

            # 处理响应格式
            if self.is_ollama:
                content = response.strip() if isinstance(response, str) else str(response).strip()
            else:
                content = response.content.strip()

            return f"## 📈 趋势分析\n\n{content}\n"
        except Exception as e:
            self.logger.warning(f"生成趋势分析失败: {str(e)}")
            return ""
    
    def _generate_insights(self, items: List[NewsItem]) -> str:
        """生成前沿洞察"""
        if self.is_ollama:
            from langchain.prompts import PromptTemplate
            prompt = PromptTemplate.from_template("""你是一个技术洞察专家。只基于今日资讯，提供3个不明显但重要的信号。

要求：
1. 每个洞察从资讯中发现隐含趋势和连接点
2. 2-3句：现象 + 深层含义 + 潜在影响
3. 避免夸大，保持客观
4. 输出格式：
**洞察1: [简短标题]**
描述...

今日资讯摘要（类别+标题）：
{summaries}

请输出3个洞察：""")
        else:
            prompt = PromptTemplate.from_template("""你是一个技术洞察专家。只基于今日资讯，提供3个不明显但重要的信号。

要求：
1. 每个洞察从2-3条资讯连接出发，发现隐含趋势
2. 2-3句：现象 + 深层含义 + 潜在影响
3. 避免夸大，保持客观
4. 输出格式：
**洞察1: [简短标题]**
描述...

今日资讯摘要（类别+标题，前15条）：
{summaries}

请输出3个洞察：""")

        try:
            # 使用所有已分析条目，而不是只用前15条
            summaries = "\n".join(
                f"- [{item.get('category', '未分类')}] {item['title']}"
                for item in items
            )
            chain = prompt | self.llm
            response = chain.invoke({"summaries": summaries})

            # 处理响应格式
            if self.is_ollama:
                content = response.strip() if isinstance(response, str) else str(response).strip()
            else:
                content = response.content.strip()

            return f"## 🔮 前沿洞察\n\n{content}\n"
        except Exception as e:
            self.logger.warning(f"生成前沿洞察失败: {str(e)}")
            return ""
    
    def _generate_predictions(self, items: List[NewsItem]) -> str:
        """生成方向预测"""
        if self.is_ollama:
            from langchain.prompts import PromptTemplate
            prompt = PromptTemplate.from_template("""你是一个技术预测专家。只基于今日资讯类别分布和标题，预测3-12个月内可能的发展方向。

要求：
1. 每个方向有明确依据（引用类别占比或具体标题）
2. 聚焦可观察变化（如产品落地、生态变化）
3. 2-3句：依据 + 预测 + 理由
4. 客观，避免绝对化
5. 输出格式：
**方向1: [标题]**
依据：...
预测：...

类别分布（降序）：
{categories}

热门标题示例：
{titles}

请输出3个方向：""")
        else:
            prompt = PromptTemplate.from_template("""你是一个技术预测专家。只基于今日资讯类别分布和标题，预测3-12个月内可能的发展方向。

要求：
1. 每个方向有明确依据（引用类别占比或具体标题）
2. 聚焦可观察变化（如产品落地、生态变化）
3. 2-3句：依据 + 预测 + 理由
4. 客观，避免绝对化
5. 输出格式：
**方向1: [标题]**
依据：...
预测：...

类别分布（降序）：
{categories}

热门标题示例：
{titles}

请输出3个方向：""")

        try:
            # 统计类别分布
            category_count = defaultdict(int)
            category_samples = defaultdict(list)

            for item in items:
                category = item.get('category', '其他')
                category_count[category] += 1
                # 为每个类别收集样本标题（增加数量以提供更全面的上下文）
                if len(category_samples[category]) < 5:  # 每个类别最多收集5个样本
                    score = item.get('quality_score', 0)
                    category_samples[category].append(f"{item['title']} (评分:{score:.1f})")

            categories = "\n".join(
                f"- {cat}: {count}条"
                for cat, count in sorted(category_count.items(), key=lambda x: x[1], reverse=True)
            )

            # 添加热门标题示例
            top_titles = "\n".join(f"- {item['title']}" for item in items[:10])  # 展示前10个标题作为示例

            chain = prompt | self.llm
            response = chain.invoke({"categories": categories, "titles": top_titles})

            # 处理响应格式
            if self.is_ollama:
                content = response.strip() if isinstance(response, str) else str(response).strip()
            else:
                content = response.content.strip()

            return f"## 🎯 方向预测\n\n{content}\n"
        except Exception as e:
            self.logger.warning(f"生成方向预测失败: {str(e)}")
            return ""
    
    def _save_report(self, content: str) -> Path:
        """保存报告"""
        filename = f"ai_robot_daily_{datetime.now().strftime('%Y%m%d')}.md"
        filepath = self.output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return filepath
