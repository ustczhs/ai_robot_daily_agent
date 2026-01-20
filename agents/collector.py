"""
信息采集Agent - 从多个来源收集AI和机器人技术资讯
"""

import logging
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote_plus
import time
import html2text
import re
import asyncio
import aiohttp

import chardet
from newsapi import NewsApiClient
import newspaper
from trafilatura import fetch_url, extract

from utils.state import NewsItem


class CollectorAgent:
    """信息采集Agent"""
    
    def __init__(self, config: dict, llm):
        self.config = config
        self.llm = llm
        self.logger = logging.getLogger(__name__)
        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = False

        # 初始化NewsAPI客户端
        newsapi_key = os.getenv(self.config['search']['newsapi']['api_key_env'])
        if newsapi_key:
            self.newsapi = NewsApiClient(api_key=newsapi_key)
            self.logger.info("NewsAPI客户端初始化成功")
        else:
            self.newsapi = None
            self.logger.warning("未找到NEWS_API_KEY环境变量，NewsAPI功能将被禁用")

    def _parse_relative_time(self, time_text: str) -> Optional[datetime]:
        """解析相对时间字符串，返回实际发布时间"""
        if not time_text:
            return None

        time_text = time_text.lower().strip()

        # 匹配各种时间格式
        patterns = [
            (r'(\d+)\s*秒前', lambda m: timedelta(seconds=int(m.group(1)))),
            (r'(\d+)\s*分钟前', lambda m: timedelta(minutes=int(m.group(1)))),
            (r'(\d+)\s*小时前', lambda m: timedelta(hours=int(m.group(1)))),
            (r'(\d+)\s*天前', lambda m: timedelta(days=int(m.group(1)))),
            (r'(\d+)\s*周前', lambda m: timedelta(weeks=int(m.group(1)))),
            (r'(\d+)\s*月前', lambda m: timedelta(days=int(m.group(1)) * 30)),  # 近似
            (r'(\d+)\s*年前', lambda m: timedelta(days=int(m.group(1)) * 365)),  # 近似
        ]

        for pattern, delta_func in patterns:
            match = re.search(pattern, time_text)
            if match:
                try:
                    delta = delta_func(match)
                    return datetime.now() - delta
                except Exception as e:
                    self.logger.debug(f"解析时间失败: {time_text}, {str(e)}")
                    continue

        # 如果无法解析，返回None
        return None
        
    def collect(self) -> List[NewsItem]:
        """收集信息 - 方案A：直接分类（用category的关键词检索，直接归类）"""
        all_items = []

        # 全局URL去重集合，避免不同关键词返回相同新闻
        seen_urls = set()

        # 从搜索引擎收集（按照categories配置进行检索和分类）
        categories = self.config['sources'].get('categories', [])
        if categories:
            engines = self.config['search'].get('engines', ['google'])

            for category_config in categories:
                category_name = category_config['name']
                category_keywords = category_config.get('keywords', [])

                if not category_keywords:
                    self.logger.warning(f"分类 '{category_name}' 没有配置关键词，跳过")
                    continue

                self.logger.info(f"开始收集分类 '{category_name}' 的内容，共 {len(category_keywords)} 个关键词")

                category_items = []

                # 对该category的所有关键词进行检索
                for keyword in category_keywords:
                    keyword_items = []

                    # 尝试每个搜索引擎
                    for engine in engines:
                        try:
                            if engine.lower() == 'newsapi':
                                items = self._search_newsapi(keyword)
                            elif engine.lower() == 'google':
                                items = self._search_google(keyword)
                            elif engine.lower() == 'bing':
                                items = self._search_bing(keyword)
                            else:
                                self.logger.warning(f"不支持的搜索引擎: {engine}")
                                continue

                            if items:  # 如果该引擎返回了结果
                                keyword_items.extend(items)
                                self.logger.debug(f"从{engine}搜索 '{keyword}' 获取 {len(items)} 条结果")
                                # 继续尝试其他引擎，提高覆盖面

                        except Exception as e:
                            self.logger.warning(f"{engine}搜索 '{keyword}' 失败: {str(e)}")
                            continue

                    # 如果所有引擎都失败，至少记录警告
                    if not keyword_items:
                        self.logger.warning(f"所有搜索引擎对关键词 '{keyword}' 都失败了")

                    # 为该关键词的结果设置分类，并加入category结果集
                    for item in keyword_items:
                        if item['url'] not in seen_urls:
                            # 直接设置分类为当前category
                            item['category'] = category_name
                            category_items.append(item)
                            seen_urls.add(item['url'])
                        else:
                            self.logger.debug(f"跳过重复URL: {item['url']}")

                    time.sleep(1)  # 关键词间避免请求过快

                self.logger.info(f"分类 '{category_name}' 收集完成，共获取 {len(category_items)} 条内容")

                # 将该category的结果加入总结果集
                all_items.extend(category_items)

                time.sleep(2)  # category间避免请求过快
        else:
            self.logger.info("未配置categories，跳过搜索引擎搜索")

        # 从指定网站收集
        try:
            website_items = self._collect_from_websites()
            # 网站内容也进行去重
            for item in website_items:
                if item['url'] not in seen_urls:
                    all_items.append(item)
                    seen_urls.add(item['url'])
                else:
                    self.logger.debug(f"跳过重复URL (网站): {item['url']}")
        except Exception as e:
            self.logger.warning(f"网站收集失败: {str(e)}")

        self.logger.info(f"搜索引擎和网站收集完成后，去重前共有 {len(all_items)} 条信息")

        # 获取完整网页内容
        try:
            self.logger.info("开始获取完整网页内容...")
            all_items = self._fetch_all_full_content(all_items)
            self.logger.info("完整网页内容获取完成")
        except Exception as e:
            self.logger.warning(f"获取完整网页内容失败: {str(e)}")

        self.logger.info(f"总共收集到 {len(all_items)} 条信息")
        return all_items
    
    def _search_google(self, keyword: str) -> List[NewsItem]:
        """通过Google搜索收集信息"""
        items = []
        max_results = self.config['search']['max_results_per_query']

        # 根据配置的max_age_hours确定搜索时间范围
        max_age_hours = self.config['filtering']['max_age_hours']

        # 选择合适的Google时间过滤器
        if max_age_hours <= 24:
            time_filter = "qdr:d"  # 最近24小时
        elif max_age_hours <= 168:  # 7天
            time_filter = "qdr:w"  # 最近一周
        elif max_age_hours <= 720:  # 30天
            time_filter = "qdr:m"  # 最近一个月
        else:
            time_filter = "qdr:y"  # 最近一年

        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        # 配置代理
        proxies = {
            'http': os.getenv('http_proxy'),
            'https': os.getenv('https_proxy')
        }

        all_items = []

        # 智能计算需要获取的页数（每页约10条结果）
        # 考虑到重复内容和质量过滤，设置一个更合理的页数上限
        max_pages = min(5, (max_results + 9) // 10)  # 最多5页，避免过度请求
        pages_needed = max_pages

        for page in range(pages_needed):
            start_index = page * 10

            # 尝试多种搜索策略来获取更多结果
            search_strategies = [
                # 策略1: 带时间限制的新闻搜索 + 分页
                f"https://www.google.com/search?q={quote_plus(keyword)}&tbm=nws&tbs={time_filter}&start={start_index}",
                # 策略2: 普通搜索带时间限制 + 分页
                f"https://www.google.com/search?q={quote_plus(keyword)}&tbs={time_filter}&start={start_index}",
                # 策略3: 不限制时间的新闻搜索 + 分页（作为备用）
                f"https://www.google.com/search?q={quote_plus(keyword)}&tbm=nws&start={start_index}",
            ]

            page_items = []
            for strategy_idx, search_url in enumerate(search_strategies):
                try:
                    self.logger.debug(f"页面 {page + 1} 策略 {strategy_idx + 1}: {search_url}")
                    response = requests.get(search_url, headers=headers, timeout=10, proxies=proxies)
                    response.raise_for_status()

                    soup = BeautifulSoup(response.text, 'html.parser')
                    strategy_items = []

                    # 解析搜索结果 - 不限制数量，尽可能获取所有结果
                    for result in soup.select('div.SoaBEf'):
                        try:
                            # 提取标题和链接
                            title_elem = result.select_one('div.n0jPhd')
                            link_elem = result.select_one('a')

                            if not title_elem or not link_elem:
                                continue

                            title = title_elem.get_text(strip=True)
                            url = link_elem.get('href', '')

                            # 提取摘要 - 尝试多种选择器
                            snippet = ""
                            for selector in ['div.GI74Re', 'div[data-ved]', 'div[data-ved] div', 'div:not([class])']:
                                snippet_elem = result.select_one(selector)
                                if snippet_elem and snippet_elem.get_text(strip=True):
                                    snippet = snippet_elem.get_text(strip=True)
                                    break

                            # 如果还是没有摘要，尝试获取整个结果的文本
                            if not snippet:
                                # 移除标题和链接，只保留其他文本
                                result_text = result.get_text()
                                title_text = title_elem.get_text()
                                # 粗略移除标题，保留其他内容
                                snippet = result_text.replace(title_text, '').strip()
                                # 限制长度
                                snippet = snippet[:300] if snippet else ""

                            # 提取来源和时间 - 尝试多种选择器
                            source = "Unknown"
                            published_date = None  # 不设置默认时间，让网页内容提取决定

                            for src_selector in ['div.CEMjEf span', 'span:not([class])', 'cite', 'span[data-ved]']:
                                source_elem = result.select_one(src_selector)
                                if source_elem:
                                    src_text = source_elem.get_text(strip=True)
                                    if src_text:
                                        # 尝试解析相对时间
                                        parsed_time = self._parse_relative_time(src_text)
                                        if parsed_time:
                                            published_date = parsed_time
                                            # 移除时间部分，只保留来源
                                            src_text = re.sub(r'\d+\s*(秒|分钟|小时|天|周|月|年)前', '', src_text).strip()
                                            if not src_text or len(src_text) > 50:
                                                src_text = "Google News"
                                        else:
                                            # 不是时间，可能是来源
                                            if len(src_text) < 50:
                                                source = src_text

                            if title and url:
                                strategy_items.append(NewsItem(
                                    title=title,
                                    url=url,
                                    content=snippet,
                                    source=source,
                                    published_date=published_date,
                                    category=None,
                                    quality_score=None,
                                    embedding=None
                                ))

                        except Exception as e:
                            self.logger.debug(f"解析搜索结果失败: {str(e)}")
                            continue

                    self.logger.debug(f"页面 {page + 1} 策略 {strategy_idx + 1} 获取 {len(strategy_items)} 条结果")

                    # 合并当前页面的结果
                    for item in strategy_items:
                        if item not in page_items:  # 当前页面内的简单去重
                            page_items.append(item)

                    # 如果当前策略获取到了结果，就不再尝试其他策略
                    if strategy_items:
                        break

                except Exception as e:
                    self.logger.debug(f"页面 {page + 1} 策略 {strategy_idx + 1} 失败: {str(e)}")
                    continue

            # 将当前页面的结果添加到总结果中
            for item in page_items:
                if item not in all_items:  # 全局去重
                    all_items.append(item)

            self.logger.debug(f"页面 {page + 1} 总共获取 {len(page_items)} 条结果，累计 {len(all_items)} 条")

            # 如果已经达到目标数量，可以提前停止
            if len(all_items) >= max_results:
                break

            # 添加延迟避免被限制
            time.sleep(1)

        # 最终去重（按标题去重）
        unique_items = []
        seen_titles = set()
        for item in all_items:
            if item['title'] not in seen_titles:
                unique_items.append(item)
                seen_titles.add(item['title'])

        items = unique_items[:max_results]  # 限制最终结果数量

        self.logger.info(f"从Google搜索 '{keyword}' 获取 {len(items)} 条结果")
        return items

    def _search_bing(self, keyword: str) -> List[NewsItem]:
        """通过Bing搜索收集信息"""
        items = []
        max_results = self.config['search']['max_results_per_query']

        # Bing新闻搜索URL - 使用国际版而不是中国版
        search_url = f"https://www.bing.com/news/search?q={quote_plus(keyword)}&form=TNSA02"

        # 使用更真实的浏览器头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }

        # 配置代理
        proxies = {
            'http': os.getenv('http_proxy'),
            'https': os.getenv('https_proxy')
        }

        try:
            self.logger.debug(f"Bing搜索URL: {search_url}")
            response = requests.get(search_url, headers=headers, timeout=15, proxies=proxies)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            all_items = []

            # 检查是否被重定向到验证码页面
            if 'sorry' in response.url.lower() or 'captcha' in response.text.lower():
                self.logger.warning("Bing返回验证码页面")
                return []

            # 解析Bing新闻搜索结果 - 使用多种选择器
            selectors = [
                'div.news-card',
                'div.caption',
                '.newsitem',
                'a[href*="/news/"]',
                'div.t_s',
                'div.t_t',
            ]

            for selector in selectors:
                for result in soup.select(selector):
                    try:
                        # 提取标题
                        title_elem = result.select_one('a.title, .title a, h2 a, a, .t_t a')
                        if not title_elem:
                            continue

                        title = title_elem.get_text(strip=True)
                        url = title_elem.get('href', '')

                        # 如果URL是相对路径，转换为绝对路径
                        if url and not url.startswith('http'):
                            url = f"https://www.bing.com{url}"

                        # 跳过非新闻链接
                        if not ('news' in url.lower() or any(domain in url.lower() for domain in ['.com', '.org', '.net', '.edu', '.gov'])):
                            continue

                        # 提取摘要
                        snippet = ""
                        snippet_selectors = ['div.snippet', '.news_snippet', 'p', '.t_d', '.caption']
                        for snip_sel in snippet_selectors:
                            snippet_elem = result.select_one(snip_sel)
                            if snippet_elem:
                                snippet = snippet_elem.get_text(strip=True)
                                break

                        # 提取来源
                        source = "Bing News"
                        source_selectors = ['span.source', '.source', '.news_source', '.t_s']
                        for src_sel in source_selectors:
                            source_elem = result.select_one(src_sel)
                            if source_elem:
                                source_text = source_elem.get_text(strip=True)
                                if source_text and len(source_text) < 100:
                                    source = source_text
                                    break

                        # 如果标题和URL都存在，且内容不为空
                        if title and url and (snippet or len(title) > 10):
                            # 清理摘要
                            if not snippet:
                                snippet = title  # 使用标题作为摘要

                            all_items.append(NewsItem(
                                title=title,
                                url=url,
                                content=snippet[:500],  # 限制长度
                                source=source,
                                published_date=None,  # 不设置默认日期，让网页内容提取决定
                                category=None,
                                quality_score=None,
                                embedding=None
                            ))

                    except Exception as e:
                        self.logger.debug(f"解析Bing搜索结果失败: {str(e)}")
                        continue

                # 如果找到结果，停止尝试其他选择器
                if all_items:
                    break

            # 去重（按标题去重）
            unique_items = []
            seen_titles = set()
            for item in all_items:
                if item['title'] not in seen_titles and len(item['title']) > 5:
                    unique_items.append(item)
                    seen_titles.add(item['title'])

            items = unique_items[:max_results]

        except Exception as e:
            self.logger.warning(f"Bing搜索失败: {str(e)}")
            return []

        self.logger.info(f"从Bing搜索 '{keyword}' 获取 {len(items)} 条结果")
        return items

    def _fetch_full_content(self, url: str) -> str:
        """获取完整内容（可选功能）"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            }
            # 配置代理
            proxies = {
                'http': os.getenv('http_proxy'),
                'https': os.getenv('https_proxy')
            }
            response = requests.get(url, headers=headers, timeout=10, proxies=proxies)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 移除脚本和样式
            for script in soup(["script", "style"]):
                script.decompose()
            
            # 提取主要内容
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            return text[:2000]  # 限制长度
            
        except Exception as e:
            self.logger.debug(f"获取完整内容失败 {url}: {str(e)}")
            return ""

    def _collect_from_websites(self) -> List[NewsItem]:
        """从指定网站收集信息"""
        items = []
        websites = self.config['sources'].get('websites', [])

        for website in websites:
            try:
                if 'arxiv.org' in website:
                    # 对每个arxiv URL分别处理，支持多条arxiv网页
                    website_items = self._collect_from_arxiv(website)
                elif 'news.ycombinator.com' in website:
                    website_items = self._collect_from_hackernews()
                elif 'reddit.com' in website:
                    website_items = self._collect_from_reddit()
                else:
                    self.logger.debug(f"不支持的网站: {website}")
                    continue

                items.extend(website_items)
                time.sleep(1)  # 避免请求过快

            except Exception as e:
                self.logger.warning(f"从 {website} 收集失败: {str(e)}")

        self.logger.info(f"从网站收集到 {len(items)} 条信息")
        return items

    def _collect_from_arxiv(self, arxiv_url: str) -> List[NewsItem]:
        """从arXiv收集AI/机器人论文"""
        items = []
        url = arxiv_url  # 使用传入的URL参数

        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        }

        proxies = {
            'http': os.getenv('http_proxy'),
            'https': os.getenv('https_proxy')
        }

        try:
            response = requests.get(url, headers=headers, timeout=10, proxies=proxies)
            response.raise_for_status()
            # 调试url，查看返回内容
            self.logger.info(f"ArXiv url: {url}")
            soup = BeautifulSoup(response.text, 'html.parser')

            # 解析论文列表
            # for entry in soup.select('div.list-title')[:10]:  # 最近10篇
            for entry in soup.select('div.list-title'):  # 最近所有论文
                try:
                    # 获取标题文本（去掉"Title:"前缀）
                    full_text = entry.get_text(strip=True)
                    if not full_text.startswith('Title:'):
                        continue

                    title = full_text[6:].strip()  # 去掉"Title:"前缀

                    # 查找对应的PDF链接来获取paper_id
                    # ArXiv页面结构：每个entry后有<dt>包含链接
                    dt_elem = entry.find_parent('dd').find_previous('dt')
                    if dt_elem:
                        pdf_link = dt_elem.select_one('a[href*="/pdf/"]')
                        if pdf_link:
                            href = pdf_link.get('href', '')
                            paper_id = href.split('/')[-1].replace('.pdf', '')  # 去掉.pdf扩展名，保留版本号
                            paper_url = f"https://arxiv.org/abs/{paper_id}"

                            # 获取摘要（在同一个<dd>中的<p class='mathjax'>）
                            dd_elem = entry.find_parent('dd')
                            abstract_elem = dd_elem.select_one('p.mathjax')
                            abstract = abstract_elem.get_text(strip=True) if abstract_elem else ""

                            if title and paper_id:
                                items.append(NewsItem(
                                    title=f"[ArXiv] {title}",
                                    url=paper_url,
                                    content=f"Abstract: {abstract[:300]}...",
                                    source="ArXiv",
                                    published_date=None,  # 不设置默认日期，让网页内容提取决定
                                    category="研究前沿与理论突破",
                                    quality_score=8.0,  # ArXiv论文通常质量较高
                                    embedding=None
                                ))

                except Exception as e:
                    self.logger.debug(f"解析ArXiv论文失败: {str(e)}")
                    continue

            self.logger.info(f"从ArXiv收集到 {len(items)} 篇论文")

        except Exception as e:
            self.logger.error(f"ArXiv收集失败: {str(e)}")

        return items

    def _collect_from_hackernews(self) -> List[NewsItem]:
        """从Hacker News收集热门文章"""
        items = []
        url = "https://news.ycombinator.com/"

        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        }

        proxies = {
            'http': os.getenv('http_proxy'),
            'https': os.getenv('https_proxy')
        }

        try:
            response = requests.get(url, headers=headers, timeout=10, proxies=proxies)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # 解析热门文章
            for story in soup.select('tr.athing')[:15]:  # 首页前15条
                try:
                    title_elem = story.select_one('a.titleline')
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    url = title_elem.get('href', '')

                    # 检查是否与AI/机器人相关
                    if any(keyword.lower() in title.lower() for keyword in
                           ['ai', 'artificial intelligence', 'machine learning', 'robot', 'neural', 'deep learning']):
                        items.append(NewsItem(
                            title=f"[HN] {title}",
                            url=url if url.startswith('http') else f"https://news.ycombinator.com/{url}",
                            content="",  # HN没有摘要
                            source="Hacker News",
                            published_date=None,  # 不设置默认日期，让网页内容提取决定
                            category=None,
                            quality_score=6.0,  # HN文章质量较好
                            embedding=None
                        ))

                except Exception as e:
                    self.logger.debug(f"解析HN文章失败: {str(e)}")
                    continue

            self.logger.info(f"从Hacker News收集到 {len(items)} 篇文章")

        except Exception as e:
            self.logger.error(f"Hacker News收集失败: {str(e)}")

        return items

    def _collect_from_reddit(self) -> List[NewsItem]:
        """从Reddit收集帖子（简化版）"""
        items = []
        # Reddit API需要特殊处理，这里先返回空列表
        self.logger.debug("Reddit收集暂未实现")
        return items

    def _fetch_all_full_content(self, items: List[NewsItem]) -> List[NewsItem]:
        """为所有新闻条目获取完整网页内容和发布时间（并发异步版本）"""
        # 使用异步方法并发获取内容
        try:
            # 创建新的事件循环或在现有循环中运行
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果已有运行中的循环，使用线程池执行器
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, self._fetch_all_full_content_async(items))
                        updated_items = future.result()
                else:
                    updated_items = asyncio.run(self._fetch_all_full_content_async(items))
            except RuntimeError:
                # 没有事件循环，创建新的
                updated_items = asyncio.run(self._fetch_all_full_content_async(items))

            return updated_items
        except Exception as e:
            self.logger.error(f"异步获取内容失败，回退到同步模式: {str(e)}")
            # 回退到同步模式
            return self._fetch_all_full_content_sync(items)

    async def _fetch_all_full_content_async(self, items: List[NewsItem]) -> List[NewsItem]:
        """异步并发获取所有网页内容"""
        updated_items = []

        # 使用信号量控制并发数量，避免过载
        semaphore = asyncio.Semaphore(15)  # 最多15个并发请求

        async def fetch_single_item(item: NewsItem, index: int) -> NewsItem:
            async with semaphore:
                try:
                    self.logger.debug(f"获取完整内容 {index+1}/{len(items)}: {item['url'][:50]}...")

                    # 使用asyncio.wait_for设置超时
                    try:
                        full_content, publish_date = await asyncio.wait_for(
                            self._fetch_article_content_async(item['url']),
                            timeout=30.0  # 30秒超时
                        )
                        item['full_content'] = full_content

                        # 如果从网页提取到了发布时间，更新published_date
                        if publish_date and isinstance(publish_date, datetime):
                            item['published_date'] = publish_date
                            self.logger.debug(f"更新发布时间为网页发布日期: {publish_date}")

                    except asyncio.TimeoutError:
                        self.logger.warning(f"获取网页内容超时，跳过: {item['url']}")
                        item['full_content'] = None

                    return item

                except Exception as e:
                    self.logger.warning(f"获取完整内容失败 {item['url']}: {str(e)}")
                    item['full_content'] = None
                    return item

        # 创建所有任务
        tasks = [fetch_single_item(item, i) for i, item in enumerate(items)]

        # 并发执行所有任务
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"异步任务执行异常: {str(result)}")
                # 为异常情况创建空的item
                empty_item = NewsItem(
                    title="Error",
                    url="",
                    content="",
                    source="Error",
                    published_date=None,
                    category=None,
                    quality_score=None,
                    embedding=None,
                    full_content=None
                )
                updated_items.append(empty_item)
            else:
                updated_items.append(result)

        # 过滤掉错误的项目
        updated_items = [item for item in updated_items if item.get('url')]

        self.logger.info(f"异步获取完成，共处理 {len(updated_items)} 条内容")
        return updated_items

    def _fetch_all_full_content_sync(self, items: List[NewsItem]) -> List[NewsItem]:
        """同步回退方法：为所有新闻条目获取完整网页内容和发布时间"""
        updated_items = []

        for i, item in enumerate(items):
            try:
                self.logger.debug(f"获取完整内容 {i+1}/{len(items)}: {item['url'][:50]}...")

                # 设置超时控制，避免单个网页卡住太久
                import signal
                from contextlib import contextmanager

                @contextmanager
                def timeout_context(seconds):
                    def timeout_handler(signum, frame):
                        raise TimeoutError(f"操作超时 {seconds} 秒")

                    signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(seconds)
                    try:
                        yield
                    finally:
                        signal.alarm(0)

                try:
                    # 为每个网页设置30秒超时
                    with timeout_context(30):
                        full_content, publish_date = self._fetch_article_content(item['url'])
                        item['full_content'] = full_content

                        # 如果从网页提取到了发布时间，更新published_date
                        if publish_date and isinstance(publish_date, datetime):
                            item['published_date'] = publish_date
                            self.logger.debug(f"更新发布时间为网页发布日期: {publish_date}")

                except TimeoutError:
                    self.logger.warning(f"获取网页内容超时，跳过: {item['url']}")
                    item['full_content'] = None

                updated_items.append(item)

                # 减少延迟时间，从0.5秒改为0.2秒
                time.sleep(0.2)

            except Exception as e:
                self.logger.warning(f"获取完整内容失败 {item['url']}: {str(e)}")
                # 即使失败也保留item，但full_content为None
                item['full_content'] = None
                updated_items.append(item)
                continue

        return updated_items

    def _extract_publish_date_from_text(self, text: str) -> Optional[datetime]:
        """从文本中提取日期（支持中英文格式）"""
        if not text:
            return None

        # 中英文月份映射
        months_en = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
            'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
        }
        months_short = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
        }
        months_zh = {
            '一月': 1, '二月': 2, '三月': 3, '四月': 4, '五月': 5, '六月': 6,
            '七月': 7, '八月': 8, '九月': 9, '十月': 10, '十一月': 11, '十二月': 12
        }

        text_lower = text.lower()

        # 优先级1: 英文缩写格式 "Jan 07, 2026" 或 "Jan 7, 2026"
        for month_short, month_num in months_short.items():
            # 匹配 "Jan 07, 2026" 格式
            pattern = rf'\b{month_short}\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b'
            match = re.search(pattern, text_lower)
            if match:
                try:
                    day = int(match.group(1))
                    year = int(match.group(2))
                    if year >= 2000 and 1 <= day <= 31:
                        return datetime(year, month_num, day)
                except:
                    continue

        # 优先级2: 英文完整格式 "January 07, 2026"
        for month_name, month_num in months_en.items():
            pattern = rf'\b{month_name}\s+(\d{{1,2}}),?\s+(\d{{4}})\b'
            match = re.search(pattern, text_lower)
            if match:
                try:
                    day = int(match.group(1))
                    year = int(match.group(2))
                    if year >= 2000 and 1 <= day <= 31:
                        return datetime(year, month_num, day)
                except:
                    continue

        # 优先级3: "Published January 07, 2026" 格式
        match = re.search(r'published\s+(\w+)\s+(\d{1,2}),?\s+(\d{4})', text_lower)
        if match:
            month_name = match.group(1)
            day = int(match.group(2))
            year = int(match.group(3))
            if month_name in months_en and year >= 2000 and 1 <= day <= 31:
                try:
                    return datetime(year, months_en[month_name], day)
                except:
                    pass

        # 优先级4: YYYY-MM-DD 或 YYYY/MM/DD
        match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', text)
        if match:
            try:
                return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except:
                pass

        # 优先级5: MM/DD/YYYY 或 DD/MM/YYYY (美国/欧洲格式)
        match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', text)
        if match:
            try:
                # 尝试美国格式 (MM/DD/YYYY)
                month, day, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
                if 1 <= month <= 12 and 1 <= day <= 31 and year >= 2000:
                    return datetime(year, month, day)
            except:
                pass

        # 优先级6: DD Month YYYY (欧洲格式)
        for month_name, month_num in months_en.items():
            pattern = rf'\b(\d{{1,2}})\s+{month_name}\s+(\d{{4}})\b'
            match = re.search(pattern, text_lower)
            if match:
                try:
                    day = int(match.group(1))
                    year = int(match.group(2))
                    return datetime(year, month_num, day)
                except:
                    continue

        # 优先级7: 中文格式 YYYY年MM月DD日
        match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
        if match:
            try:
                return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except:
                pass

        # 优先级8: YYYY年MM月 (中文年月格式，取当月1日)
        match = re.search(r'(\d{4})年(\d{1,2})月', text)
        if match:
            try:
                return datetime(int(match.group(1)), int(match.group(2)), 1)
            except:
                pass

        return None

    def extract_36kr_publish_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        """
        从36Kr移动端文章中提取真正的发布时间

        36Kr移动端特点：
        - 几乎不用标准的meta标签
        - 日期在标题下方，作者后面，带·分隔符
        - 格式：作者名 · YYYY年MM月DD日 HH:MM
        """
        # 存储所有候选日期 [(datetime, confidence_score, source)]
        candidates = []

        # 优先级1: 寻找标题下方的作者-时间行（最可靠）
        title_candidates = self._find_title_nearby_dates_36kr(soup)
        candidates.extend(title_candidates)

        # 优先级2: CSS选择器暴力搜索（中等可靠）
        css_candidates = self._find_css_selector_dates_36kr(soup)
        candidates.extend(css_candidates)

        # 优先级3: 正则表达式全文本搜索（兜底）
        regex_candidates = self._find_regex_dates_36kr(soup)
        candidates.extend(regex_candidates)

        if not candidates:
            self.logger.debug("36Kr日期提取: 未找到任何候选日期")
            return None

        # 按置信度排序，选择最佳候选
        candidates.sort(key=lambda x: x[1], reverse=True)  # 按置信度降序
        best_candidate = candidates[0]
        best_date, confidence, source = best_candidate

        self.logger.debug(f"36Kr日期提取: 选择最佳候选 - {best_date} (置信度:{confidence}, 来源:{source})")

        # 最终验证：日期不能太早或太晚
        now = datetime.now()
        if best_date.year < 2010 or best_date > now:
            self.logger.warning(f"36Kr日期提取: 日期不合理 {best_date}, 放弃")
            return None

        return best_date

    def _find_title_nearby_dates_36kr(self, soup: BeautifulSoup) -> List[Tuple[datetime, int, str]]:
        """优先级1: 寻找标题下方的作者-时间行"""
        candidates = []

        # 寻找标题元素
        title_selectors = ['h1', '.title', '.article-title', '[class*="title"]']
        title_elem = None

        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                self.logger.debug(f"找到标题元素: {selector}")
                break

        if not title_elem:
            self.logger.debug("未找到标题元素")
            return candidates

        # 从标题元素开始，向下搜索兄弟元素和子元素
        search_elements = []

        # 标题的下一个兄弟元素
        sibling = title_elem.find_next_sibling()
        if sibling:
            search_elements.append((sibling, 95))  # 高置信度

        # 标题父元素的下一个兄弟
        parent_sibling = title_elem.parent.find_next_sibling() if title_elem.parent else None
        if parent_sibling:
            search_elements.append((parent_sibling, 90))

        # 包含info/meta/detail类的元素
        info_selectors = ['.info', '.meta', '.detail', '.author', '.article-info', '.detail-info']
        for selector in info_selectors:
            info_elems = soup.select(selector)
            for elem in info_elems[:3]:  # 只看前3个
                search_elements.append((elem, 85))

        # 检查这些元素中的文本
        for elem, base_confidence in search_elements:
            text = elem.get_text(strip=True)
            if not text:
                continue

            self.logger.debug(f"检查元素文本: {text[:50]}...")

            # 特别处理带·分隔符的行（36Kr特征）
            if '·' in text:
                parts = text.split('·')
                for part in parts[1:]:  # ·后面的部分
                    date = self._parse_date_string_36kr(part.strip())
                    if date:
                        candidates.append((date, base_confidence + 10, f"标题附近·分隔符"))
                        break

            # 普通文本中的日期
            date = self._parse_date_string_36kr(text)
            if date:
                candidates.append((date, base_confidence, f"标题附近文本"))

        return candidates

    def _find_css_selector_dates_36kr(self, soup: BeautifulSoup) -> List[Tuple[datetime, int, str]]:
        """优先级2: CSS选择器暴力搜索"""
        candidates = []

        # 36Kr常见的作者-时间行选择器
        selectors = [
            '.author', '.info', '.meta', '.detail-info', '.article-info',
            '.publish-time', '.article-time', '.time'
        ]

        for selector in selectors:
            try:
                elements = soup.select(selector)
                for elem in elements[:5]:  # 每个选择器最多检查5个元素
                    text = elem.get_text(strip=True)
                    if not text:
                        continue

                    self.logger.debug(f"CSS选择器 {selector}: {text[:50]}...")

                    # 优先处理·分隔符
                    if '·' in text:
                        parts = text.split('·')
                        for part in parts:
                            date = self._parse_date_string_36kr(part.strip())
                            if date:
                                candidates.append((date, 80, f"CSS·分隔符:{selector}"))
                                break

                    # 普通日期
                    date = self._parse_date_string_36kr(text)
                    if date:
                        candidates.append((date, 70, f"CSS文本:{selector}"))

            except Exception as e:
                self.logger.debug(f"CSS选择器 {selector} 失败: {e}")

        return candidates

    def _find_regex_dates_36kr(self, soup: BeautifulSoup) -> List[Tuple[datetime, int, str]]:
        """优先级3: 正则表达式全文本搜索"""
        candidates = []

        # 获取页面主要内容文本（排除script/style）
        for script in soup(["script", "style"]):
            script.decompose()

        text = soup.get_text()

        # 正则模式（按优先级排序）
        patterns = [
            # 带时间的完整格式
            (r'(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{1,2})', 65, "中文完整时间"),
            (r'(\d{4})-(\d{1,2})-(\d{1,2})\s*(\d{1,2}):(\d{1,2})', 60, "ISO完整时间"),

            # 只带日期的格式
            (r'(\d{4})年(\d{1,2})月(\d{1,2})日', 55, "中文日期"),
            (r'(\d{4})-(\d{1,2})-(\d{1,2})', 50, "ISO日期"),

            # 年月格式（取当月1日）
            (r'(\d{4})年(\d{1,2})月', 30, "中文年月"),
        ]

        for pattern, confidence, source in patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                try:
                    groups = match.groups()
                    if len(groups) >= 3:
                        year = int(groups[0])
                        month = int(groups[1])
                        day = int(groups[2]) if len(groups) > 2 else 1
                        hour = int(groups[3]) if len(groups) > 3 else 0
                        minute = int(groups[4]) if len(groups) > 4 else 0

                        # 验证日期合理性
                        if 2010 <= year <= datetime.now().year and 1 <= month <= 12 and 1 <= day <= 31:
                            try:
                                date = datetime(year, month, day, hour, minute)
                                candidates.append((date, confidence, f"正则:{source}"))
                            except ValueError:
                                continue  # 无效日期如2月30日

                except (ValueError, IndexError) as e:
                    self.logger.debug(f"正则解析失败: {match.group()} - {e}")
                    continue

        # 如果没找到高质量候选，尝试全文最早的合法日期（兜底）
        if not candidates or max(c[1] for c in candidates) < 40:
            earliest_date = self._find_earliest_valid_date_36kr(text)
            if earliest_date:
                candidates.append((earliest_date, 25, "全文最早日期"))

        return candidates

    def _parse_date_string_36kr(self, text: str) -> Optional[datetime]:
        """解析单个日期字符串"""
        text = text.strip()

        # 中文完整格式: 2018年01月04日 19:14
        match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{1,2})', text)
        if match:
            try:
                return datetime(
                    int(match.group(1)), int(match.group(2)), int(match.group(3)),
                    int(match.group(4)), int(match.group(5))
                )
            except ValueError:
                pass

        # 中文日期格式: 2018年01月04日
        match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
        if match:
            try:
                return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                pass

        # ISO完整格式: 2018-01-04 19:14
        match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})\s*(\d{1,2}):(\d{1,2})', text)
        if match:
            try:
                return datetime(
                    int(match.group(1)), int(match.group(2)), int(match.group(3)),
                    int(match.group(4)), int(match.group(5))
                )
            except ValueError:
                pass

        # ISO日期格式: 2018-01-04
        match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', text)
        if match:
            try:
                return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                pass

        return None

    def _find_earliest_valid_date_36kr(self, text: str) -> Optional[datetime]:
        """兜底：找全文最早的合法日期"""
        # 只找2010年后的日期，避免抓到历史事件
        pattern = r'\b(20[1-9]\d)[-/年](\d{1,2})[-/月](\d{1,2})日?\b'
        matches = re.finditer(pattern, text)

        valid_dates = []
        for match in matches:
            try:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3))

                if year >= 2010 and month <= 12 and day <= 31:
                    date = datetime(year, month, day)
                    valid_dates.append(date)
            except ValueError:
                continue

        if valid_dates:
            earliest = min(valid_dates)
            self.logger.debug(f"找到全文最早日期: {earliest}")
            return earliest

        return None

    def _extract_publish_date_with_llm(self, text: str, llm) -> Optional[datetime]:
        """使用LLM智能提取日期"""
        if not text or not llm:
            return None

        # 准备prompt - 只提取前1000字符的关键文本
        text_sample = text[:1000]

        prompt = f"""你是一个专业的日期提取专家。请从以下网页文本中找出文章的发布日期。

要求：
1. 只返回日期，格式为 YYYY-MM-DD
2. 如果找不到明确的发布日期，返回 "NO_DATE"
3. 忽略所有时间部分（小时、分钟），只返回日期
4. 日期必须是文章的原始发布日期，不是更新日期

网页文本：
{text_sample}

请返回日期（只返回 YYYY-MM-DD 或 NO_DATE）："""

        try:
            response = llm.invoke(prompt)
            result = response.content.strip() if hasattr(response, 'content') else str(response).strip()
            print(f"LLM日期提取响应: {result}")
            # 清理响应
            result = result.replace('```', '').strip()
            if result == "NO_DATE" or len(result) < 8:
                return None

            # 尝试解析日期
            try:
                return datetime.strptime(result, '%Y-%m-%d')
            except:
                self.logger.debug(f"LLM返回的日期格式无效: {result}")
                return None

        except Exception as e:
            self.logger.debug(f"LLM日期提取失败: {str(e)}")
            return None

    def _extract_publish_date_from_url(self, url: str) -> Optional[datetime]:
        """从URL路径中提取日期"""
        if not url:
            return None

        # 匹配常见的URL日期模式
        patterns = [
            r'/(\d{4})/(\d{1,2})/(\d{1,2})/',  # /2026/01/08/
            r'/(\d{4})-(\d{1,2})-(\d{1,2})/',  # /2026-01-08/
            r'/(\d{4})/(\d{2})(\d{2})/',       # /20260108/
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                try:
                    year = int(match.group(1))
                    month = int(match.group(2))
                    day = int(match.group(3))
                    if 2000 <= year <= 2030 and 1 <= month <= 12 and 1 <= day <= 31:
                        return datetime(year, month, day)
                except:
                    continue

        return None

    def _extract_publish_date_from_html(self, html_content: str) -> Optional[datetime]:
        """从HTML内容中提取发布时间"""
        if not html_content:
            return None

        soup = BeautifulSoup(html_content, 'html.parser')

        # 优先级1: Open Graph article:published_time
        meta_published = soup.find('meta', property='article:published_time')
        if meta_published and meta_published.get('content'):
            try:
                content = meta_published['content']
                # 处理ISO格式和常见格式
                if 'T' in content:
                    return datetime.fromisoformat(content.replace('Z', '+00:00'))
                else:
                    return datetime.strptime(content, '%Y-%m-%d')
            except:
                pass

        # 优先级2: 其他常见的meta标签
        meta_tags = [
            ('name', 'publishdate'),
            ('name', 'date'),
            ('name', 'pubdate'),
            ('property', 'og:article:published_time'),
            ('itemprop', 'datePublished')
        ]

        for attr, value in meta_tags:
            meta = soup.find('meta', {attr: value})
            if meta and meta.get('content'):
                try:
                    content = meta['content']
                    # 尝试不同的时间格式
                    formats = ['%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']
                    for fmt in formats:
                        try:
                            return datetime.strptime(content, fmt)
                        except:
                            continue
                except:
                    continue

        # 优先级3: <time>标签
        time_elem = soup.find('time')
        if time_elem:
            datetime_attr = time_elem.get('datetime') or time_elem.get('pubdate')
            if datetime_attr:
                try:
                    if 'T' in datetime_attr:
                        return datetime.fromisoformat(datetime_attr.replace('Z', '+00:00'))
                    else:
                        return datetime.strptime(datetime_attr, '%Y-%m-%d')
                except:
                    pass

        # 优先级4: JSON-LD结构化数据
        script_tags = soup.find_all('script', type='application/ld+json')
        for script in script_tags:
            try:
                import json
                data = json.loads(script.string)
                if isinstance(data, dict):
                    # 处理单个对象
                    date_published = data.get('datePublished')
                    if date_published:
                        try:
                            if 'T' in date_published:
                                return datetime.fromisoformat(date_published.replace('Z', '+00:00'))
                            else:
                                return datetime.strptime(date_published, '%Y-%m-%d')
                        except:
                            pass
                elif isinstance(data, list):
                    # 处理数组
                    for item in data:
                        if isinstance(item, dict):
                            date_published = item.get('datePublished')
                            if date_published:
                                try:
                                    if 'T' in date_published:
                                        return datetime.fromisoformat(date_published.replace('Z', '+00:00'))
                                    else:
                                        return datetime.strptime(date_published, '%Y-%m-%d')
                                except:
                                    pass
            except:
                continue

        return None

    def _fetch_article_content(self, url: str) -> tuple[Optional[str], Optional[datetime]]:
        """使用htmldate、newspaper3k和trafilatura获取文章完整内容和发布时间"""
        if not url or not url.startswith(('http://', 'https://')):
            return None, None

        publish_date = None
        html_content = None

        # 首先获取原始HTML，并进行编码检测和纠正
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            }
            proxies = {
                'http': os.getenv('http_proxy'),
                'https': os.getenv('https_proxy')
            }
            response = requests.get(url, headers=headers, timeout=10, proxies=proxies)
            response.raise_for_status()

            # 检测网页编码并尝试多种解码方式
            detected_encoding = chardet.detect(response.content)['encoding']
            confidence = chardet.detect(response.content)['confidence']
            self.logger.debug(f"检测到网页编码: {detected_encoding} (置信度: {confidence:.2f})")

            # 尝试多种编码来正确解码中文内容，按优先级排序
            encodings_to_try = [
                detected_encoding,  # 检测到的编码优先
                'utf-8',           # UTF-8最常见
                'gbk',             # 中文GBK编码
                'gb2312',          # 中文GB2312编码
                'big5',            # 繁体中文Big5
                'iso-8859-1',      # 西欧编码
                'windows-1252',    # Windows西欧编码
                'latin1'           # 拉丁编码
            ]

            html_content = None
            best_encoding = None

            for encoding in encodings_to_try:
                if not encoding:
                    continue
                try:
                    html_content = response.content.decode(encoding)
                    # 验证解码质量：检查是否有明显的乱码特征
                    invalid_chars = ['', '', '', '']  # UTF-8解码错误的常见字符
                    has_invalid_chars = any(char in html_content for char in invalid_chars)

                    # 检查是否包含正常的中文字符（作为解码成功的指标）
                    has_chinese = any('\u4e00' <= char <= '\u9fff' for char in html_content)

                    # 如果没有乱码字符，或者包含中文字符，认为是成功解码
                    if not has_invalid_chars or has_chinese or encoding == 'utf-8':
                        best_encoding = encoding
                        self.logger.debug(f"成功使用编码 {encoding} 解码网页")
                        break
                except (UnicodeDecodeError, LookupError):
                    continue

            if html_content is None:
                self.logger.warning("所有编码尝试都失败，使用response.text作为最后的后备方案")
                html_content = response.text  # 最后的fallback
                best_encoding = 'fallback'

        except Exception as e:
            self.logger.debug(f"获取HTML内容失败: {str(e)}")
            return None, None

        # 优先级1: 针对36Kr移动端特殊处理（最高优先级）
        if 'm.36kr.com' in url:
            soup = BeautifulSoup(html_content, 'html.parser')
            publish_date = self.extract_36kr_publish_date(soup)
            if publish_date:
                self.logger.debug(f"从36Kr专用提取器提取到发布时间: {publish_date}")

        # 优先级2: 使用htmldate提取日期（最准确）
        if not publish_date:
            try:
                from htmldate import find_date
                date_str = find_date(html_content, extensive_search=True, original_date=True)
                if date_str:
                    try:
                        # htmldate返回YYYY-MM-DD格式
                        extracted_date = datetime.strptime(date_str, '%Y-%m-%d')
                        # 验证htmldate结果的合理性
                        now = datetime.now()
                        if extracted_date.year >= 2010 and extracted_date <= now:
                            publish_date = extracted_date
                            self.logger.debug(f"从htmldate提取到发布时间: {publish_date}")
                        else:
                            self.logger.debug(f"htmldate提取到不合理日期，跳过: {extracted_date}")
                    except:
                        pass
            except Exception as e:
                self.logger.debug(f"htmldate提取失败: {str(e)}")

        # 优先级3: 如果htmldate失败，从URL提取日期
        if not publish_date:
            publish_date = self._extract_publish_date_from_url(url)
            if publish_date:
                self.logger.debug(f"从URL提取到发布时间: {publish_date}")

        # 优先级3: 使用HTML元数据提取
        if not publish_date:
            publish_date = self._extract_publish_date_from_html(html_content)
            if publish_date:
                self.logger.debug(f"从HTML元数据提取到发布时间: {publish_date}")

        # 优先级4: 使用LLM智能提取日期（放宽条件，提高覆盖率）
        if not publish_date:
            publish_date = self._extract_publish_date_with_llm(html_content, self.llm)
            if publish_date:
                self.logger.debug(f"从LLM提取到发布时间: {publish_date}")
            else:
                self.logger.debug("LLM未能提取到日期")

        # 优先级5: 从页面文本提取日期（regex作为最后fallback）
        if not publish_date:
            # 提取页面开头部分的文本来搜索日期
            soup = BeautifulSoup(html_content, 'html.parser')
            # 移除脚本和样式
            for script in soup(["script", "style"]):
                script.decompose()
            page_text = soup.get_text()[:2000]  # 只检查前2000字符
            publish_date = self._extract_publish_date_from_text(page_text)
            if publish_date:
                self.logger.debug(f"从页面文本(regex)提取到发布时间: {publish_date}")

        # 尝试使用newspaper3k获取内容
        try:
            self.logger.debug(f"使用newspaper3k抓取: {url}")
            article = newspaper.Article(url, language='en')
            article.set_html(html_content)
            article.parse()

            if article.text and len(article.text.strip()) > 100:
                content = article.text.strip()
                # 限制长度，避免过长
                content = content[:5000] if len(content) > 5000 else content

                # 如果还没提取到时间，使用newspaper3k的时间作为备选
                if not publish_date and article.publish_date:
                    publish_date = article.publish_date
                    self.logger.debug(f"从newspaper3k提取到发布时间: {publish_date}")

                return content, publish_date

        except Exception as e:
            self.logger.debug(f"newspaper3k失败: {str(e)}")

        # newspaper3k失败，尝试trafilatura
        try:
            self.logger.debug(f"使用trafilatura抓取: {url}")
            content = extract(html_content, include_comments=False, include_tables=False,
                            date_extraction_params={'extensive_search': True, 'original_date': True})
            if content and len(content.strip()) > 100:
                # 清理内容
                content = content.strip()
                content = content[:5000] if len(content) > 5000 else content

                return content, publish_date

        except Exception as e:
            self.logger.debug(f"trafilatura失败: {str(e)}")

        # 所有方法都失败，返回None
        return None, publish_date

    async def _fetch_article_content_async(self, url: str) -> tuple[Optional[str], Optional[datetime]]:
        """异步版本：使用htmldate、newspaper3k和trafilatura获取文章完整内容和发布时间"""
        if not url or not url.startswith(('http://', 'https://')):
            return None, None

        publish_date = None
        html_content = None

        # 配置代理
        proxy_url = os.getenv('http_proxy') or os.getenv('https_proxy')

        # 首先获取原始HTML，并进行编码检测和纠正
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            }

            # 使用aiohttp进行异步请求
            connector = aiohttp.TCPConnector(limit_per_host=10)  # 限制每个主机的连接数
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10),
                                     proxy=proxy_url) as response:
                    response.raise_for_status()

                    # 获取响应内容
                    content = await response.read()

                    # 检测网页编码并尝试多种解码方式
                    detected_encoding = chardet.detect(content)['encoding']
                    confidence = chardet.detect(content)['confidence']
                    self.logger.debug(f"检测到网页编码: {detected_encoding} (置信度: {confidence:.2f})")

                    # 尝试多种编码来正确解码中文内容，按优先级排序
                    encodings_to_try = [
                        detected_encoding,  # 检测到的编码优先
                        'utf-8',           # UTF-8最常见
                        'gbk',             # 中文GBK编码
                        'gb2312',          # 中文GB2312编码
                        'big5',            # 繁体中文Big5
                        'iso-8859-1',      # 西欧编码
                        'windows-1252',    # Windows西欧编码
                        'latin1'           # 拉丁编码
                    ]

                    html_content = None
                    best_encoding = None

                    for encoding in encodings_to_try:
                        if not encoding:
                            continue
                        try:
                            html_content = content.decode(encoding)
                            # 验证解码质量：检查是否有明显的乱码特征
                            invalid_chars = ['', '', '', '']  # UTF-8解码错误的常见字符
                            has_invalid_chars = any(char in html_content for char in invalid_chars)

                            # 检查是否包含正常的中文字符（作为解码成功的指标）
                            has_chinese = any('\u4e00' <= char <= '\u9fff' for char in html_content)

                            # 如果没有乱码字符，或者包含中文字符，认为是成功解码
                            if not has_invalid_chars or has_chinese or encoding == 'utf-8':
                                best_encoding = encoding
                                self.logger.debug(f"成功使用编码 {encoding} 解码网页")
                                break
                        except (UnicodeDecodeError, LookupError):
                            continue

                    if html_content is None:
                        self.logger.warning("所有编码尝试都失败，使用默认解码")
                        html_content = content.decode('utf-8', errors='ignore')  # 最后的fallback

        except Exception as e:
            self.logger.debug(f"异步获取HTML内容失败: {str(e)}")
            return None, None

        # 优先级1: 针对36Kr移动端特殊处理（最高优先级）
        if 'm.36kr.com' in url:
            soup = BeautifulSoup(html_content, 'html.parser')
            publish_date = self.extract_36kr_publish_date(soup)
            if publish_date:
                self.logger.debug(f"从36Kr专用提取器提取到发布时间: {publish_date}")

        # 优先级2: 使用htmldate提取日期（最准确）
        if not publish_date:
            try:
                from htmldate import find_date
                date_str = find_date(html_content, extensive_search=True, original_date=True)
                if date_str:
                    try:
                        # htmldate返回YYYY-MM-DD格式
                        extracted_date = datetime.strptime(date_str, '%Y-%m-%d')
                        # 验证htmldate结果的合理性
                        now = datetime.now()
                        if extracted_date.year >= 2010 and extracted_date <= now:
                            publish_date = extracted_date
                            self.logger.debug(f"从htmldate提取到发布时间: {publish_date}")
                        else:
                            self.logger.debug(f"htmldate提取到不合理日期，跳过: {extracted_date}")
                    except:
                        pass
            except Exception as e:
                self.logger.debug(f"htmldate提取失败: {str(e)}")

        # 优先级2: 如果htmldate失败，从URL提取日期
        if not publish_date:
            publish_date = self._extract_publish_date_from_url(url)
            if publish_date:
                self.logger.debug(f"从URL提取到发布时间: {publish_date}")

        # 优先级3: 使用HTML元数据提取
        if not publish_date:
            publish_date = self._extract_publish_date_from_html(html_content)
            if publish_date:
                self.logger.debug(f"从HTML元数据提取到发布时间: {publish_date}")

        # 优先级4: 使用LLM智能提取日期（放宽条件，提高覆盖率）
        if not publish_date:
            publish_date = self._extract_publish_date_with_llm(html_content, self.llm)
            if publish_date:
                self.logger.debug(f"从LLM提取到发布时间: {publish_date}")
            else:
                self.logger.debug("LLM未能提取到日期")

        # 优先级5: 从页面文本提取日期（regex作为最后fallback）
        if not publish_date:
            # 提取页面开头部分的文本来搜索日期
            soup = BeautifulSoup(html_content, 'html.parser')
            # 移除脚本和样式
            for script in soup(["script", "style"]):
                script.decompose()
            page_text = soup.get_text()[:2000]  # 只检查前2000字符
            publish_date = self._extract_publish_date_from_text(page_text)
            if publish_date:
                self.logger.debug(f"从页面文本(regex)提取到发布时间: {publish_date}")

        # 尝试使用newspaper3k获取内容
        try:
            self.logger.debug(f"使用newspaper3k抓取: {url}")
            article = newspaper.Article(url, language='en')
            article.set_html(html_content)
            article.parse()

            if article.text and len(article.text.strip()) > 100:
                content = article.text.strip()
                # 限制长度，避免过长
                content = content[:5000] if len(content) > 5000 else content

                # 如果还没提取到时间，使用newspaper3k的时间作为备选
                if not publish_date and article.publish_date:
                    publish_date = article.publish_date
                    self.logger.debug(f"从newspaper3k提取到发布时间: {publish_date}")

                return content, publish_date

        except Exception as e:
            self.logger.debug(f"newspaper3k失败: {str(e)}")

        # newspaper3k失败，尝试trafilatura
        try:
            self.logger.debug(f"使用trafilatura抓取: {url}")
            content = extract(html_content, include_comments=False, include_tables=False,
                            date_extraction_params={'extensive_search': True, 'original_date': True})
            if content and len(content.strip()) > 100:
                # 清理内容
                content = content.strip()
                content = content[:5000] if len(content) > 5000 else content

                return content, publish_date

        except Exception as e:
            self.logger.debug(f"trafilatura失败: {str(e)}")

        # 所有方法都失败，返回None
        return None, publish_date

    def _search_newsapi(self, keyword: str) -> List[NewsItem]:
        """通过NewsAPI收集信息"""
        items = []

        if not self.newsapi:
            self.logger.warning("NewsAPI客户端未初始化")
            return items

        # 测试阶段：每个关键词只调用1次
        calls_per_keyword = self.config['search']['newsapi']['calls_per_keyword']
        if calls_per_keyword <= 0:
            self.logger.debug(f"NewsAPI调用次数限制为0，跳过关键词: {keyword}")
            return items

        max_results = self.config['search']['max_results_per_query']
        language = self.config['search']['newsapi']['language']
        sort_by = self.config['search']['newsapi']['sort_by']

        try:
            # 调用NewsAPI - 只调用1次
            self.logger.debug(f"调用NewsAPI搜索关键词: {keyword}")
            response = self.newsapi.get_everything(
                q=keyword,
                language=language,
                sort_by=sort_by,
                page_size=min(max_results, 10),  # 限制每次最多10条
                page=1
            )

            if response['status'] != 'ok':
                self.logger.warning(f"NewsAPI返回错误: {response.get('message', 'Unknown error')}")
                return items

            articles = response.get('articles', [])
            self.logger.debug(f"NewsAPI返回 {len(articles)} 条结果")

            for article in articles:
                try:
                    title = article.get('title', '').strip()
                    url = article.get('url', '').strip()
                    description = article.get('description', '').strip()
                    source_name = article.get('source', {}).get('name', 'NewsAPI')

                    # 解析发布时间
                    published_at = article.get('publishedAt', '')
                    try:
                        published_date = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                    except:
                        published_date = datetime.now()

                    if title and url and (description or len(title) > 10):
                        # 清理描述
                        content = description if description else title

                        items.append(NewsItem(
                            title=title,
                            url=url,
                            content=content[:500],  # 限制长度
                            source=source_name,
                            published_date=published_date,
                            category=None,
                            quality_score=None,
                            embedding=None
                        ))

                except Exception as e:
                    self.logger.debug(f"解析NewsAPI文章失败: {str(e)}")
                    continue

            # 限制结果数量
            items = items[:max_results]

        except Exception as e:
            self.logger.warning(f"NewsAPI搜索失败: {str(e)}")
            return []

        self.logger.info(f"从NewsAPI搜索 '{keyword}' 获取 {len(items)} 条结果")
        return items
