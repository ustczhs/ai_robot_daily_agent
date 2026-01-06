#!/usr/bin/env python3
"""
测试Google搜索内容解析和分析功能 - 使用真实搜索结果
"""

import os
import sys
import yaml
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from agents.collector import CollectorAgent
from agents.analyzer import AnalyzerAgent
from agents.reporter import ReporterAgent
from utils.state import NewsItem


class MockLLM:
    """模拟LLM类，用于测试"""
    pass


def load_config():
    """加载配置文件"""
    config_path = Path('./config/config.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def test_google_parsing_and_analysis():
    """测试Google搜索解析和分析功能"""
    print("=" * 80)
    print("🧪 测试Google搜索内容解析和分析功能")
    print("=" * 80)

    try:
        # 加载配置
        config = load_config()
        print("✅ 配置文件加载成功")

        # 检查环境变量
        api_key = os.getenv('DASHSCOPE_API_KEY') or os.getenv('OPENAI_API_KEY')
        if not api_key:
            print("❌ 未找到API密钥，请设置环境变量")
            print("   export DASHSCOPE_API_KEY='your-key'")
            return False

        print("✅ API密钥已设置")

        # 检查代理设置
        http_proxy = os.getenv('http_proxy')
        https_proxy = os.getenv('https_proxy')

        if http_proxy and https_proxy:
            print("✅ 代理已设置")
        else:
            print("⚠️  代理未设置，Google搜索可能失败")

        # 创建模拟LLM（用于CollectorAgent）
        mock_llm = MockLLM()

        # 创建CollectorAgent实例
        collector = CollectorAgent(config, mock_llm)
        print("✅ CollectorAgent实例创建成功")

        # 测试Google搜索 - 使用一个简单的关键词
        test_keyword = "CES 2026"
        print(f"\n🔍 测试Google搜索关键词: '{test_keyword}'")

        search_results = []
        try:
            search_results = collector._search_google(test_keyword)
            print(f"📊 Google搜索返回 {len(search_results)} 条结果")

            if len(search_results) == 0:
                print("❌ Google搜索失败，可能的原因:")
                print("   - 代理设置问题")
                print("   - 网络连接问题")
                print("   - Google服务屏蔽")
                return False

            # 验证搜索结果结构
            print("\n📋 验证搜索结果结构:")
            valid_count = 0
            for i, item in enumerate(search_results, 1):  # 检查所有结果
                print(f"\n{i}. 标题: {item['title']}")
                print(f"   来源: {item['source']}")
                print(f"   URL: {item['url']}")
                print(f"   内容: {item['content'][:100]}...")
                print(f"   发布时间: {item['published_date']}")

                # 检查必需字段
                required_fields = ['title', 'url', 'content', 'source', 'published_date']
                missing_fields = [field for field in required_fields if field not in item]
                if missing_fields:
                    print(f"   ❌ 缺少字段: {missing_fields}")
                else:
                    print("   ✅ 数据结构完整")
                    valid_count += 1

            if valid_count == len(search_results):
                print("\n✅ Google搜索结果结构验证通过")
            else:
                print(f"\n⚠️  部分结果结构不完整: {valid_count}/{len(search_results)}")

        except Exception as e:
            print(f"❌ Google搜索测试失败: {str(e)}")
            return False

        # 创建真实的LLM用于分析
        from langchain_openai import ChatOpenAI

        real_llm = ChatOpenAI(
            model=config['llm']['model'],
            temperature=config['llm']['temperature'],
            max_tokens=config['llm']['max_tokens'],
            openai_api_base=config['llm'].get('base_url'),
            openai_api_key=api_key
        )

        # 测试内容分析
        print("\n🔍 测试内容分析功能...")
        analyzer = AnalyzerAgent(config, real_llm)
        print("✅ AnalyzerAgent实例创建成功")

        # 分析搜索结果（限制数量避免API调用过多）
        test_items = search_results[:2]  # 只分析前2条
        print(f"📊 分析 {len(test_items)} 条搜索结果")

        analyzed_items = []
        try:
            # 手动分析每条内容，打印调试信息
            for i, item in enumerate(test_items, 1):
                print(f"\n📝 分析第{i}条内容:")
                print(f"   标题: {item['title']}")
                print(f"   内容: {item['content'][:200]}...")

                try:
                    # 直接调用分析方法
                    chain = analyzer.prompt | analyzer.llm
                    response = chain.invoke({
                        "title": item['title'],
                        "content": item['content'][:500],
                        "source": item['source'],
                        "categories": "\n".join(f"- {cat}" for cat in analyzer.categories),
                        "format_instructions": analyzer.parser.get_format_instructions()
                    })

                    print(f"   🔍 LLM原始响应: {response.content}")

                    # 尝试解析
                    analysis = analyzer.parser.parse(response.content)
                    print(f"   📊 解析结果: 评分={analysis.quality_score}, 相关={analysis.is_relevant}, 分类={analysis.category}")
                    print(f"   💬 理由: {analysis.reason}")

                    # 更新条目信息
                    item['category'] = analysis.category
                    item['quality_score'] = analysis.quality_score

                    # 检查是否满足过滤条件
                    if analysis.is_relevant and analysis.quality_score >= analyzer.min_quality_score:
                        analyzed_items.append(item)
                        print("   ✅ 通过过滤")
                    else:
                        print(f"   ❌ 被过滤 (相关={analysis.is_relevant}, 评分={analysis.quality_score} < {analyzer.min_quality_score})")

                except Exception as e:
                    print(f"   ❌ 分析失败: {str(e)}")

            print(f"\n✅ 内容分析完成，返回 {len(analyzed_items)} 条高质量内容")

            # 验证分析结果
            print("\n📋 分析结果验证:")
            for i, item in enumerate(analyzed_items, 1):
                print(f"\n{i}. 标题: {item['title'][:60]}...")
                print(f"   评分: {item.get('quality_score', 'N/A')}")
                print(f"   分类: {item.get('category', 'N/A')}")

                # 检查分析后新增的字段
                if 'quality_score' in item and 'category' in item:
                    print("   ✅ 分析字段完整")
                else:
                    print("   ❌ 分析字段缺失")

        except Exception as e:
            print(f"❌ 内容分析测试失败: {str(e)}")
            return False

        # 测试报告生成
        print("\n📝 测试报告生成功能...")
        reporter = ReporterAgent(config, real_llm)
        print("✅ ReporterAgent实例创建成功")

        try:
            report_path = reporter.generate_report(analyzed_items)
            print(f"✅ 报告生成成功: {report_path}")

            # 检查报告文件是否存在
            if Path(report_path).exists():
                print("✅ 报告文件已创建")

                # 读取报告内容进行简单验证
                with open(report_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                if len(content) > 1000:  # 合理的报告长度
                    print("✅ 报告内容长度正常")
                else:
                    print("⚠️  报告内容较短，可能存在问题")

            else:
                print("❌ 报告文件未创建")
                return False

        except Exception as e:
            print(f"❌ 报告生成测试失败: {str(e)}")
            return False

        print("\n🎉 所有Google解析和分析测试通过!")
        return True

    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("🔧 环境检查...")
    print(f"Python版本: {sys.version}")
    print(f"工作目录: {os.getcwd()}")

    # 运行测试
    success = test_google_parsing_and_analysis()

    if success:
        print("\n🎉 Google搜索解析和分析功能测试成功!")
        print("✅ HTML解析正常")
        print("✅ 内容分析正常")
        print("✅ 报告生成正常")
    else:
        print("\n💥 测试失败!")
        print("请检查:")
        print("- API密钥设置")
        print("- 代理配置")
        print("- 网络连接")
        sys.exit(1)


if __name__ == "__main__":
    main()
