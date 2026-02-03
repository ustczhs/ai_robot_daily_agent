import requests
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
import os
from typing import List, Dict

# 模拟你的 NewsItem（如果你项目里有，就用原来的；这里简化成 dict）
class SimpleItem(Dict):
    def __init__(self, title="", url="", content="", source=""):
        super().__init__()
        self['title'] = title
        self['url'] = url
        self['content'] = content
        self['source'] = source

def search_bing_web(keyword: str, max_results: int = 10) -> List[SimpleItem]:
    items = []

    # 普通网页搜索 URL（推荐加 mkt=en-US 避免过度本地化）
    search_url = f"https://www.bing.com/search?q={quote_plus(keyword)}&form=QBLH&mkt=en-US"

    # headers（升级到较新版本，减少被软限概率）
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Referer': 'https://www.bing.com/',
    }

    proxies = {}
    if os.getenv('http_proxy') and os.getenv('https_proxy'):
        proxies = {
            'http': os.getenv('http_proxy'),
            'https': os.getenv('https_proxy'),
        }
        print("使用代理:", proxies)

    try:
        print(f"请求 URL: {search_url}")
        response = requests.get(search_url, headers=headers, proxies=proxies, timeout=15)
        print(f"Status Code: {response.status_code}")
        print(f"最终 URL (重定向后): {response.url}")
        print(f"页面长度: {len(response.text)} 字节")

        if response.status_code != 200:
            print("请求失败，返回内容预览：")
            print(response.text[:500])
            return []

        soup = BeautifulSoup(response.text, 'html.parser')

        # 检查常见反爬提示（可选）
        if "captcha" in response.text.lower() or "sorry" in response.url.lower():
            print("警告：可能触发了验证码或阻断页")
            return []

        # Bing 网页搜索的核心选择器：li.b_algo （非常稳定）
        results = soup.select('li.b_algo')
        print(f"找到 li.b_algo 数量: {len(results)}")

        all_items = []
        seen_urls = set()

        for result in results:
            try:
                # 标题和链接（最常见结构）
                title_elem = result.select_one('h2 a')
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                url = title_elem.get('href', '')

                if not url:
                    continue

                if url in seen_urls:
                    continue
                seen_urls.add(url)

                # 摘要
                snippet = ""
                snippet_elem = result.select_one('div.b_caption p, p')
                if snippet_elem:
                    snippet = snippet_elem.get_text(strip=True).strip()

                # 来源 / 显示 URL
                source = "Bing Web"
                cite = result.select_one('cite')
                if cite:
                    source = cite.get_text(strip=True)

                if title and url:
                    item = SimpleItem(
                        title=title,
                        url=url,
                        content=snippet[:500],
                        source=source
                    )
                    all_items.append(item)

            except Exception as e:
                print(f"解析单个结果出错: {e}")
                continue

        # 取前 max_results 条
        items = all_items[:max_results]

    except Exception as e:
        print(f"整体请求/解析失败: {e}")
        return []

    print(f"\n从 Bing 网页搜索 '{keyword}' 获取到 {len(items)} 条有效结果\n")
    for i, item in enumerate(items, 1):
        print(f"[{i}] {item['title']}")
        print(f"    URL: {item['url']}")
        print(f"    来源: {item['source']}")
        print(f"    摘要: {item['content'][:150]}..." if item['content'] else "无摘要")
        print("-" * 60)

    return items


if __name__ == "__main__":
    # 测试关键词（你可以改成任意）
    test_keywords = [
        "Tesla stock January 2026",
        "AI 发展趋势 2026",
        "新加坡 天气 预报 2026",
    ]

    for kw in test_keywords:
        print(f"\n===== 测试关键词: {kw} =====")
        search_bing_web(kw, max_results=8)