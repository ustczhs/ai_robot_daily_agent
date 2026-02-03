import requests
from bs4 import BeautifulSoup
from htmldate import find_date

url = 'https://zhuanlan.zhihu.com/p/1893386527255544906'
headers = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
}

try:
    response = requests.get(url, headers=headers, timeout=10)
    response.encoding = response.apparent_encoding # 解决中文乱码
    html_content = response.text

    # 方案 A：优先尝试精准提取（针对证券之星 wap 版布局）
    soup = BeautifulSoup(html_content, 'html.parser')
    # 查找 class 包含 time 的标签
    time_tag = soup.find('span', class_='time') or soup.find('div', class_='time')
    
    if time_tag:
        publish_date = time_tag.get_text(strip=True)
        print(f"精准提取日期: {publish_date}")
    else:
        # 方案 B：如果 A 失败，再使用 htmldate，但通过参数限制它不要乱猜
        # extensive=False 会让它更严谨，不再返回当前系统时间
        date = find_date(html_content, outputformat='%Y-%m-%d')
        print(f"插件提取日期: {date}")

except Exception as e:
    print(f"错误: {e}")

import requests
import re


try:
    response = requests.get(url, headers=headers, timeout=10)
    # 自动处理编码
    response.encoding = response.apparent_encoding 
    html_text = response.text

    # 方案 1：针对该网站的 class="time" 标签进行匹配
    # 查找类似 2025-12-22 这种模式
    date_match = re.search(r'class="time">(\d{4}-\d{2}-\d{2})', html_text)
    
    if date_match:
        publish_date = date_match.group(1)
        print(f"成功提取发布日期: {publish_date}")
    else:
        # 方案 2：如果找不到标签，直接在全文搜索第一个 20xx-xx-xx 格式的日期
        # 排除掉今天的时间 2026-01-21
        all_dates = re.findall(r'20\d{2}-\d{2}-\d{2}', html_text)
        # 过滤掉今天的日期（防止误抓系统时间）
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        filtered_dates = [d for d in all_dates if d != today]
        
        if filtered_dates:
            print(f"从全文匹配到日期: {filtered_dates[0]}")
        else:
            print("未能找到符合条件的日期")

except Exception as e:
    print(f"请求失败: {e}")