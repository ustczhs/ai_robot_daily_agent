"""
报告生成Agent - 生成结构化的技术日报
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict
from collections import defaultdict
import asyncio
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

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

        # 初始化远程LLM用于分析方法
        analysis_provider = self.config['report'].get('analysis_llm_provider', 'remote')
        if analysis_provider == 'remote':
            self.remote_llm = ChatOpenAI(
                model="qwen-max",  # 使用qwen-max进行高质量分析
                temperature=0.3,  # 分析需要更确定性的输出
                max_tokens=4000,
                openai_api_base=config['llm'].get('base_url'),
                openai_api_key=os.getenv('DASHSCOPE_API_KEY') or os.getenv('OPENAI_API_KEY')
            )
            self.logger.info("分析方法将使用远程LLM: qwen-max")
        else:
            # 如果配置为ollama，则使用传入的llm
            self.remote_llm = llm
            self.logger.info("分析方法将使用本地LLM: ollama")
        
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
        """构建报告内容（并发点评生成版本）"""
        # 使用异步方法并发生成点评
        try:
            # 创建新的事件循环或在现有循环中运行
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果已有运行中的循环，使用线程池执行器
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, self._build_report_async(categorized, all_items))
                        report_content = future.result()
                else:
                    report_content = asyncio.run(self._build_report_async(categorized, all_items))
            except RuntimeError:
                # 没有事件循环，创建新的
                report_content = asyncio.run(self._build_report_async(categorized, all_items))

            return report_content
        except Exception as e:
            self.logger.error(f"异步构建报告失败，回退到同步模式: {str(e)}")
            # 回退到同步模式
            return self._build_report_sync(categorized, all_items)

    async def _build_report_async(self, categorized: Dict[str, List[NewsItem]], all_items: List[NewsItem]) -> str:
        """异步构建报告内容"""
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

        # 收集所有需要生成点评的条目
        items_to_comment = []
        for category, items in categorized.items():
            max_items = self.config['report']['max_items_per_category']
            items_to_comment.extend(items[:max_items])

        self.logger.info(f"开始并发生成 {len(items_to_comment)} 条点评")

        # 并发生成所有点评
        comments_dict = await self._generate_comments_concurrent(items_to_comment)

        # 按类别生成内容
        max_items = self.config['report']['max_items_per_category']

        for category, items in categorized.items():
            report += f"\n### {category}\n\n"

            for i, item in enumerate(items[:max_items], 1):
                # 从并发结果中获取点评
                comment = comments_dict.get(item['url'])
                if comment is None:
                    self.logger.debug(f"跳过非技术内容: {item['title']}")
                    continue  # 跳过这个条目，不计入总数

                # 翻译标题为简体中文
                translated_title = self._translate_title(item['title'])
                # 打印输出item的全部context内容以供调试
                self.logger.info(f"生成点评 - content: {item['content']}...")
                self.logger.info(f"生成点评 - full_content: {item['full_content']}...")
                report += f"{i}. **[{translated_title}][{item['title']}]\n({item['url']})**\n"
                report += f"   - 📰 来源: {item['source']}\n"

                # 添加发布时间显示
                published_date = item.get('published_date')
                if published_date and isinstance(published_date, datetime):
                    # 格式化为中文时间格式
                    time_str = published_date.strftime('%Y年%m月%d日')
                    report += f"   - 🕒 发布时间: {time_str}\t"
                else:
                    report += f"   - 🕒 发布时间: 未知\t"

                report += f"   - ⭐ 评分: {item.get('quality_score', 0):.1f}/10\n"
                report += f"   - 💬 简介: {comment}\n\n"

        # 生成分析部分（这些可以串行执行，因为通常数量少）
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

    async def _generate_comments_concurrent(self, items: List[NewsItem]) -> Dict[str, str]:
        """并发生成多个条目的点评"""
        comments_dict = {}

        # 使用信号量控制并发数量，避免LLM服务过载
        semaphore = asyncio.Semaphore(8)  # 最多8个并发点评生成

        async def generate_single_comment(item: NewsItem) -> tuple[str, str]:
            async with semaphore:
                try:
                    comment = await self._generate_comment_async(item)
                    return item['url'], comment
                except Exception as e:
                    self.logger.warning(f"异步生成点评失败 {item['url']}: {str(e)}")
                    return item['url'], None

        # 创建所有任务
        tasks = [generate_single_comment(item) for item in items]

        # 并发执行所有任务
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"异步点评任务执行异常: {str(result)}")
            else:
                url, comment = result
                comments_dict[url] = comment

        self.logger.info(f"并发点评生成完成，共处理 {len(comments_dict)} 条")
        return comments_dict

    def _build_report_sync(self, categorized: Dict[str, List[NewsItem]], all_items: List[NewsItem]) -> str:
        """同步回退方法：构建报告内容"""
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
                # 生成点评，如果不技术相关则跳过
                comment = self._generate_comment(item)
                if comment is None:
                    self.logger.debug(f"跳过非技术内容: {item['title']}")
                    continue  # 跳过这个条目，不计入总数

                # 翻译标题为简体中文
                translated_title = self._translate_title(item['title'])
                # 打印输出item的全部context内容以供调试
                self.logger.info(f"生成点评 - content: {item['content']}...")
                self.logger.info(f"生成点评 - full_content: {item['full_content']}...")
                report += f"{i}. **[{translated_title}][{item['title']}]\n({item['url']})**\n"
                report += f"   - 📰 来源: {item['source']}\n"

                # 添加发布时间显示
                published_date = item.get('published_date')
                if published_date and isinstance(published_date, datetime):
                    # 格式化为中文时间格式
                    time_str = published_date.strftime('%Y年%m月%d日')
                    report += f"   - 🕒 发布时间: {time_str}\t"
                else:
                    report += f"   - 🕒 发布时间: 未知\t"

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
    
    def _translate_title(self, title: str) -> str:
        """翻译标题为简体中文"""
        if not self.is_ollama:
            # 如果不是ollama，直接返回原标题
            return title

        from langchain.prompts import PromptTemplate
        prompt = PromptTemplate.from_template("""请将以下标题翻译为简体中文，保持专业性和准确性。只输出翻译后的标题，不要添加任何其他内容。

标题：{title}

翻译：""")

        try:
            chain = prompt | self.llm
            response = chain.invoke({"title": title})

            # 处理ollama响应格式
            if isinstance(response, str):
                translated = response.strip()
            elif hasattr(response, 'content') and response.content:
                translated = response.content.strip()
            else:
                translated = str(response).strip()

            # 清理可能的额外内容，只保留第一行
            translated = translated.split('\n')[0].strip()

            if translated:
                return translated
            else:
                self.logger.warning(f"标题翻译失败，返回原标题: {title}")
                return title

        except Exception as e:
            self.logger.error(f"翻译标题失败: {str(e)}")
            return title

    def _generate_comment(self, item: NewsItem) -> str:
        """生成详细点评和内容介绍"""
        if self.is_ollama:
            # Ollama使用简单的字符串提示词
            from langchain.prompts import PromptTemplate
            prompt = PromptTemplate.from_template("""你是一个技术新闻摘要器。只根据提供的标题、内容、来源，用简体中文写100-200字技术总结。
任务：
1. 生成100-200字技术点评，包含核心技术/产品/创新点和应用场景
2. 判断内容是否与机器人/AI/自动化的技术直接相关

严禁添加原文没有的信息、任何数字、性能指标、推测内容。

输出格式：
点评：[100-200字技术总结]
是否技术相关：[是/否]
                                                  
标题：{title}
内容：{content}
来源：{source}

输出：""")
            # prompt = PromptTemplate.from_template("""你是一个技术新闻摘要器。只根据提供的标题、内容、来源，用简体中文写100-200字技术总结，只总结不判断。

            # 必须包含：
            # - 概括核心技术/产品/创新点
            # - 1-2句说明实际意义或应用场景（只说原文提到的）
            # - 重点关注提及的产品名称及特点                                                  

            # 严禁添加原文没有的信息、任何数字、性能指标、推测内容。

            # 标题：{title}
            # 内容：{content}
            # 来源：{source}

            # 输出：""")
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
                # 解析响应，检查是否技术相关
                if self._is_technical_comment(content):
                    # 提取点评内容，移除判断部分
                    comment_part = self._extract_comment_from_response(content)
                    return comment_part
                else:
                    self.logger.debug(f"内容不技术相关，已过滤: {item['title']}")
                    return None  # 标记为不技术相关
            else:
                self.logger.warning("LLM返回内容为空")
                return None

        except Exception as e:
            self.logger.error(f"生成点评失败: {str(e)}")
            return "值得关注的技术进展"

    async def _generate_comment_async(self, item: NewsItem) -> str:
        """异步生成详细点评和内容介绍"""
        # 注意：由于langchain的LLM调用不支持原生异步，我们使用线程池来异步执行
        import concurrent.futures

        def sync_generate():
            return self._generate_comment(item)

        # 使用线程池执行器来异步运行同步LLM调用
        with concurrent.futures.ThreadPoolExecutor() as executor:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(executor, sync_generate)
            return result
    
    def _generate_trend_analysis(self, items: List[NewsItem]) -> str:
        """生成趋势分析"""
        analysis_provider = self.config['report'].get('analysis_llm_provider', 'remote')

        if analysis_provider == 'ollama':  # 使用Ollama
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
        else:  # 使用远程LLM
            from langchain.prompts import PromptTemplate
            prompt = PromptTemplate.from_template("""你是一个技术趋势分析专家。只基于今日提供的资讯标题和类别分布，提炼3个核心趋势。

要求：
1. 严格从标题中提取热点（如具身智能、家庭机器人、陪伴机器人等），避免外部知识
2. 每个趋势2-3句：先描述现象（引用1-2条标题），再分析原因/影响
3. 专业易懂，无推测性语言
4. 可联网进行内容校验，但请勿重复
5. 输出格式：
**趋势1: [标题]**
描述...

今日资讯标题：
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

            chain = prompt | self.remote_llm
            response = chain.invoke({"titles": titles, "categories": categories})

            # 根据配置决定响应处理方式
            if analysis_provider == 'remote':
                content = response.content.strip()
            else:
                # Ollama响应处理
                content = response.strip() if isinstance(response, str) else str(response).strip()

            return f"## 📈 趋势分析\n\n{content}\n"
        except Exception as e:
            self.logger.warning(f"生成趋势分析失败: {str(e)}")
            return ""
    
    def _generate_insights(self, items: List[NewsItem]) -> str:
        """生成前沿洞察"""
        analysis_provider = self.config['report'].get('analysis_llm_provider', 'remote')

        if analysis_provider == 'ollama':  # 使用Ollama
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
        else:  # 使用远程LLM
            from langchain.prompts import PromptTemplate
            prompt = PromptTemplate.from_template("""你是一个技术洞察专家。只基于今日资讯，提供3个不明显但重要的信号。

要求：
1. 每个洞察从2-3条资讯连接出发，发现隐含趋势
2. 2-3句：现象 + 深层含义 + 潜在影响
3. 避免夸大，保持客观
4. 可联网进行校验，避免重复
5. 输出格式：
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
            chain = prompt | self.remote_llm
            response = chain.invoke({"summaries": summaries})

            # 根据配置决定响应处理方式
            if analysis_provider == 'remote':
                content = response.content.strip()
            else:
                # Ollama响应处理
                content = response.strip() if isinstance(response, str) else str(response).strip()

            return f"## 🔮 前沿洞察\n\n{content}\n"
        except Exception as e:
            self.logger.warning(f"生成前沿洞察失败: {str(e)}")
            return ""
    
    def _generate_predictions(self, items: List[NewsItem]) -> str:
        """生成方向预测"""
        analysis_provider = self.config['report'].get('analysis_llm_provider', 'remote')

        if analysis_provider == 'ollama':  # 使用Ollama
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
        else:  # 使用远程LLM
            from langchain.prompts import PromptTemplate
            prompt = PromptTemplate.from_template("""你是一个技术预测专家。只基于今日资讯类别分布和标题，预测3-12个月内可能的发展方向。

要求：
1. 每个方向有明确依据（引用类别占比或具体标题）
2. 聚焦可观察变化（如产品落地、生态变化）
3. 2-3句：依据 + 预测 + 理由
4. 客观，避免绝对化
5. 可联网进行校验，避免重复
6. 输出格式：
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

            chain = prompt | self.remote_llm
            response = chain.invoke({"categories": categories, "titles": top_titles})

            # 根据配置决定响应处理方式
            if analysis_provider == 'remote':
                content = response.content.strip()
            else:
                # Ollama响应处理
                content = response.strip() if isinstance(response, str) else str(response).strip()

            return f"## 🎯 方向预测\n\n{content}\n"
        except Exception as e:
            self.logger.warning(f"生成方向预测失败: {str(e)}")
            return ""

    def _is_technical_comment(self, content: str) -> bool:
        """检查点评内容是否技术相关"""
        if not content:
            return False

        # 对于Ollama的结构化响应，检查是否技术相关标记
        if "是否技术相关：" in content:
            if "是否技术相关：是" in content:
                return True
            elif "是否技术相关：否" in content:
                return False

        # 对于远程LLM或其他情况，检查内容是否包含技术关键词
        tech_indicators = [
            '技术', '算法', 'AI', '人工智能', '机器人', '自动化',
            '传感器', '控制器', '芯片', '处理器', '软件', '硬件',
            '创新', '研发', '产品', '应用', '解决方案'
        ]

        content_lower = content.lower()
        tech_count = sum(1 for indicator in tech_indicators if indicator in content_lower)

        # 如果包含2个或以上技术指标，认为技术相关
        return tech_count >= 2

    def _extract_comment_from_response(self, content: str) -> str:
        """从LLM响应中提取点评内容"""
        if not content:
            return ""

        # 对于Ollama的结构化响应，提取点评部分
        if "点评：" in content and "是否技术相关：" in content:
            # 找到点评部分
            start_marker = "点评："
            end_marker = "是否技术相关："

            start_idx = content.find(start_marker)
            end_idx = content.find(end_marker)

            if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
                comment = content[start_idx + len(start_marker):end_idx].strip()
                return comment

        # 对于其他情况，返回完整内容
        return content.strip()

    def _save_report(self, content: str) -> Path:
        """保存报告"""
        filename = f"ai_robot_daily_{datetime.now().strftime('%Y%m%d')}.md"
        filepath = self.output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return filepath
