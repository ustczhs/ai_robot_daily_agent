"""
信息采集Agent - 从多个来源收集AI和机器人技术资讯
"""

import logging
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from urllib.parse import quote_plus
import time
import html2text
import re

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
        """收集信息"""
        all_items = []

        # 从搜索引擎收集
        engines = self.config['search'].get('engines', ['google'])
        for keyword in self.config['sources']['keywords']:
            keyword_items = []

            # 尝试每个搜索引擎（全部执行，提高覆盖面）
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
                        self.logger.info(f"从{engine}搜索 '{keyword}' 获取 {len(items)} 条结果")
                        # 继续尝试其他引擎，提高覆盖面

                except Exception as e:
                    self.logger.warning(f"{engine}搜索 '{keyword}' 失败: {str(e)}")
                    continue

            # 如果所有引擎都失败，至少记录警告
            if not keyword_items:
                self.logger.warning(f"所有搜索引擎对 '{keyword}' 都失败了")

            all_items.extend(keyword_items)
            time.sleep(2)  # 避免请求过快

        # 从指定网站收集
        try:
            website_items = self._collect_from_websites()
            all_items.extend(website_items)
        except Exception as e:
            self.logger.warning(f"网站收集失败: {str(e)}")

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

        # 尝试多种搜索策略来获取更多结果
        search_strategies = [
            # 策略1: 默认新闻搜索（最近48小时）
            f"https://www.google.com/search?q={quote_plus(keyword)}&tbm=nws&tbs=qdr:d2",
            # 策略2: 更宽泛的时间范围（最近一周）
            f"https://www.google.com/search?q={quote_plus(keyword)}&tbm=nws&tbs=qdr:w",
            # 策略3: 不限制时间
            f"https://www.google.com/search?q={quote_plus(keyword)}&tbm=nws",
            # 策略4: 普通搜索（可能返回更多结果）
            f"https://www.google.com/search?q={quote_plus(keyword)}&tbs=qdr:d2",
        ]
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        # 配置代理
        proxies = {
            'http': os.getenv('http_proxy'),
            'https': os.getenv('https_proxy')
        }

        all_items = []
        for strategy_idx, search_url in enumerate(search_strategies):
            try:
                self.logger.debug(f"尝试搜索策略 {strategy_idx + 1}: {search_url}")
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
                        published_date = datetime.now()  # 默认使用当前时间

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

                self.logger.debug(f"策略 {strategy_idx + 1} 获取 {len(strategy_items)} 条结果")

                # 合并结果，避免重复
                for item in strategy_items:
                    if item not in all_items:  # 简单去重
                        all_items.append(item)

                # 如果已经达到目标数量，可以提前停止
                if len(all_items) >= max_results:
                    break

            except Exception as e:
                self.logger.debug(f"搜索策略 {strategy_idx + 1} 失败: {str(e)}")
                continue

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
                                published_date=datetime.now(),
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
                                    published_date=datetime.now(),
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
                            published_date=datetime.now(),
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
        """为所有新闻条目获取完整网页内容和发布时间"""
        updated_items = []

        for i, item in enumerate(items):
            try:
                self.logger.debug(f"获取完整内容 {i+1}/{len(items)}: {item['url'][:50]}...")
                full_content, publish_date = self._fetch_article_content(item['url'])
                item['full_content'] = full_content

                # 如果从网页提取到了发布时间，更新published_date
                if publish_date and isinstance(publish_date, datetime):
                    item['published_date'] = publish_date
                    self.logger.debug(f"更新发布时间为网页发布日期: {publish_date}")

                updated_items.append(item)

                # 添加短暂延迟，避免请求过快
                time.sleep(0.5)

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

        # 首先获取原始HTML
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
            html_content = response.text

        except Exception as e:
            self.logger.debug(f"获取HTML内容失败: {str(e)}")
            return None, None

        # 优先级1: 使用htmldate提取日期（最准确）
        try:
            from htmldate import find_date
            date_str = find_date(html_content, extensive_search=True, original_date=True)
            if date_str:
                try:
                    # htmldate返回YYYY-MM-DD格式
                    publish_date = datetime.strptime(date_str, '%Y-%m-%d')
                    self.logger.debug(f"从htmldate提取到发布时间: {publish_date}")
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

        # 优先级4: 使用LLM智能提取日期
        if not publish_date:
            publish_date = self._extract_publish_date_with_llm(html_content, self.llm)
            if publish_date:
                self.logger.debug(f"从LLM提取到发布时间: {publish_date}")

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
