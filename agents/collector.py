"""
信息采集Agent - 从多个来源收集AI和机器人技术资讯
"""

import logging
import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict
from urllib.parse import quote_plus
import time
import html2text

from utils.state import NewsItem


class CollectorAgent:
    """信息采集Agent"""
    
    def __init__(self, config: dict, llm):
        self.config = config
        self.llm = llm
        self.logger = logging.getLogger(__name__)
        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = False
        
    def collect(self) -> List[NewsItem]:
        """收集信息"""
        all_items = []

        # 从Google搜索收集
        for keyword in self.config['sources']['keywords']:
            try:
                items = self._search_google(keyword)
                all_items.extend(items)
                time.sleep(2)  # 避免请求过快
            except Exception as e:
                self.logger.warning(f"搜索 '{keyword}' 失败: {str(e)}")

        # 从指定网站收集
        try:
            website_items = self._collect_from_websites()
            all_items.extend(website_items)
        except Exception as e:
            self.logger.warning(f"网站收集失败: {str(e)}")

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

                        # 提取来源 - 尝试多种选择器
                        source = "Unknown"
                        for src_selector in ['div.CEMjEf span', 'span:not([class])', 'cite', 'span[data-ved]']:
                            source_elem = result.select_one(src_selector)
                            if source_elem:
                                src_text = source_elem.get_text(strip=True)
                                if src_text and len(src_text) < 50:  # 合理的来源长度
                                    source = src_text
                                    break

                        if title and url:
                            strategy_items.append(NewsItem(
                                title=title,
                                url=url,
                                content=snippet,
                                source=source,
                                published_date=datetime.now(),
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
                    website_items = self._collect_from_arxiv()
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

    def _collect_from_arxiv(self) -> List[NewsItem]:
        """从arXiv收集AI论文"""
        items = []
        url = "https://arxiv.org/list/cs.AI/recent"

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

            # 解析论文列表
            for entry in soup.select('div.list-title')[:10]:  # 最近10篇
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
