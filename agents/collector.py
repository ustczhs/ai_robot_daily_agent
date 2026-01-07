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

    def _fetch_all_full_content(self, items: List[NewsItem]) -> List[NewsItem]:
        """为所有新闻条目获取完整网页内容"""
        updated_items = []

        for i, item in enumerate(items):
            try:
                self.logger.debug(f"获取完整内容 {i+1}/{len(items)}: {item['url'][:50]}...")
                full_content = self._fetch_article_content(item['url'])
                item['full_content'] = full_content
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

    def _fetch_article_content(self, url: str) -> Optional[str]:
        """使用newspaper3k和trafilatura获取文章完整内容"""
        if not url or not url.startswith(('http://', 'https://')):
            return None

        # 尝试使用newspaper3k（适合新闻网站）
        try:
            self.logger.debug(f"使用newspaper3k抓取: {url}")
            article = newspaper.Article(url, language='en')
            article.download()
            article.parse()

            if article.text and len(article.text.strip()) > 100:
                content = article.text.strip()
                # 限制长度，避免过长
                return content[:5000] if len(content) > 5000 else content

        except Exception as e:
            self.logger.debug(f"newspaper3k失败: {str(e)}")

        # newspaper3k失败，尝试trafilatura
        try:
            self.logger.debug(f"使用trafilatura抓取: {url}")
            downloaded = fetch_url(url)
            if downloaded:
                content = extract(downloaded, include_comments=False, include_tables=False)
                if content and len(content.strip()) > 100:
                    # 清理内容
                    content = content.strip()
                    return content[:5000] if len(content) > 5000 else content

        except Exception as e:
            self.logger.debug(f"trafilatura失败: {str(e)}")

        # 两个工具都失败，返回None
        return None

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
