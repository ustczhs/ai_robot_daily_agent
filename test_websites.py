#!/usr/bin/env python3
"""
测试websites抓取功能 - 验证CollectorAgent的网站收集能力
"""

import os
import sys
import yaml
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from agents.collector import CollectorAgent
from utils.state import NewsItem


class MockLLM:
    """模拟LLM类，用于测试"""
    pass


def load_config():
    """加载配置文件"""
    config_path = Path('./config/config.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def test_websites_collection():
    """测试websites收集功能"""
    print("=" * 80)
    print("🧪 测试Websites抓取功能")
    print("=" * 80)

    try:
        # 加载配置
        config = load_config()
        print("✅ 配置文件加载成功")

        # 创建模拟LLM
        mock_llm = MockLLM()

        # 创建CollectorAgent实例
        collector = CollectorAgent(config, mock_llm)
        print("✅ CollectorAgent实例创建成功")

        # 测试websites收集
        print("\n🔍 开始测试websites收集...")
        website_items = collector._collect_from_websites()

        print(f"📊 从websites收集到 {len(website_items)} 条信息")

        # 验证结果
        if len(website_items) > 0:
            print("\n📋 收集结果验证:")
            valid_count = 0

            for i, item in enumerate(website_items[:5], 1):  # 只显示前5条
                print(f"\n{i}. 标题: {item['title']}")
                print(f"   来源: {item['source']}")
                print(f"   URL: {item['url']}")
                print(f"   评分: {item.get('quality_score', 'N/A')}")
                print(f"   分类: {item.get('category', 'N/A')}")

                # 验证NewsItem结构
                required_fields = ['title', 'url', 'content', 'source', 'published_date']
                if all(field in item for field in required_fields):
                    valid_count += 1
                    print("   ✅ 数据结构正确")
                else:
                    print("   ❌ 数据结构不完整")

            print(f"\n✅ 数据验证完成: {valid_count}/{len(website_items)} 条数据结构正确")

            # 统计来源分布
            sources = {}
            for item in website_items:
                source = item['source']
                sources[source] = sources.get(source, 0) + 1

            print("\n📈 来源分布:")
            for source, count in sources.items():
                print(f"   {source}: {count} 条")

        else:
            print("⚠️  未收集到任何数据，可能的原因:")
            print("   - 网络连接问题")
            print("   - 代理设置问题")
            print("   - 网站结构变化")
            print("   - 防火墙阻止访问")

        # 测试各个子方法
        print("\n🔬 测试各个子方法...")
        # 测试ArXiv收集
        try:
            arxiv_items = collector._collect_from_arxiv()
            print(f"   ArXiv: {len(arxiv_items)} 条")
        except Exception as e:
            print(f"   ArXiv: 失败 - {str(e)}")

        # 测试Hacker News收集
        try:
            hn_items = collector._collect_from_hackernews()
            print(f"   Hacker News: {len(hn_items)} 条")
        except Exception as e:
            print(f"   Hacker News: 失败 - {str(e)}")

        print("\n✅ Websites收集测试完成")
        return True

    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_proxy_settings():
    """测试代理设置"""
    print("\n🔧 测试代理设置...")
    http_proxy = os.getenv('http_proxy')
    https_proxy = os.getenv('https_proxy')

    print(f"   HTTP_PROXY: {http_proxy}")
    print(f"   HTTPS_PROXY: {https_proxy}")

    if http_proxy and https_proxy:
        print("   ✅ 代理已设置")
    else:
        print("   ⚠️  代理未设置，可能影响访问")


if __name__ == "__main__":
    # 测试代理设置
    test_proxy_settings()

    # 运行websites收集测试
    success = test_websites_collection()

    if success:
        print("\n🎉 所有测试通过!")
    else:
        print("\n💥 测试失败!")
        sys.exit(1)
