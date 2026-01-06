#!/usr/bin/env python3
"""
测试运行脚本 - 使用少量数据测试Agent功能
"""

import os
import sys
from datetime import datetime

# 模拟运行，不实际调用API
os.environ.setdefault('OPENAI_API_KEY', 'test-key')

from utils.state import NewsItem

# 创建测试数据
test_items = [
    NewsItem(
        title="OpenAI发布GPT-5预览版，多模态能力大幅提升",
        url="https://example.com/news1",
        content="OpenAI今天发布了GPT-5的预览版本，新模型在多模态理解、推理能力和代码生成方面都有显著提升...",
        source="TechCrunch",
        published_date=datetime.now(),
        category="大语言模型与生成式AI",
        quality_score=9.2,
        embedding=None
    ),
    NewsItem(
        title="波士顿动力推出新一代人形机器人Atlas 2.0",
        url="https://example.com/news2",
        content="波士顿动力公司发布了新一代人形机器人Atlas 2.0，具备更强的平衡能力和灵活性...",
        source="IEEE Spectrum",
        published_date=datetime.now(),
        category="机器人技术与具身智能",
        quality_score=8.8,
        embedding=None
    ),
    NewsItem(
        title="Meta开源Segment Anything Model 2，视频分割精度提升40%",
        url="https://example.com/news3",
        content="Meta AI开源了SAM 2模型，支持视频级别的对象分割，在多个基准测试中超越前代...",
        source="VentureBeat",
        published_date=datetime.now(),
        category="计算机视觉",
        quality_score=8.5,
        embedding=None
    )
]

print("=" * 80)
print("🧪 测试数据生成")
print("=" * 80)
print(f"\n生成了 {len(test_items)} 条测试数据：\n")

for i, item in enumerate(test_items, 1):
    print(f"{i}. [{item['category']}] {item['title']}")
    print(f"   评分: {item['quality_score']}/10")
    print()

print("✅ 测试数据准备完成")
print("\n提示：实际运行时，请确保设置正确的OPENAI_API_KEY环境变量")
print("      export OPENAI_API_KEY='your-actual-api-key'")
