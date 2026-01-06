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
        
        self.logger.info(f"总共收集到 {len(all_items)} 条信息")
        return all_items
    
    def _search_google(self, keyword: str) -> List[NewsItem]:
        """通过Google搜索收集信息"""
        items = []
        max_results = self.config['search']['max_results_per_query']
        
        # 限制搜索时间范围（最近48小时）
        search_url = f"https://www.google.com/search?q={quote_plus(keyword)}&tbm=nws&tbs=qdr:d2"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        # 配置代理
        proxies = {
            'http': os.getenv('http_proxy'),
            'https': os.getenv('https_proxy')
        }

        try:
            response = requests.get(search_url, headers=headers, timeout=10, proxies=proxies)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 解析搜索结果
            for result in soup.select('div.SoaBEf')[:max_results]:
                try:
                    # 提取标题和链接
                    title_elem = result.select_one('div.n0jPhd')
                    link_elem = result.select_one('a')
                    
                    if not title_elem or not link_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    url = link_elem.get('href', '')
                    
                    # 提取摘要
                    snippet_elem = result.select_one('div.GI74Re')
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    
                    # 提取来源
                    source_elem = result.select_one('div.CEMjEf span')
                    source = source_elem.get_text(strip=True) if source_elem else "Unknown"
                    
                    if title and url:
                        items.append(NewsItem(
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
            
            self.logger.info(f"从Google搜索 '{keyword}' 获取 {len(items)} 条结果")
            
        except Exception as e:
            self.logger.error(f"Google搜索失败: {str(e)}")
        
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
