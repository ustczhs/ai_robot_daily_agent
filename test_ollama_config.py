#!/usr/bin/env python3
"""
测试Ollama配置是否正常工作
"""

import os
import sys
import yaml
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

try:
    from langchain_ollama import OllamaLLM
except ImportError:
    print("❌ 缺少依赖，请安装 langchain-ollama")
    print("pip install langchain-ollama")
    sys.exit(1)


def load_config():
    """加载配置文件"""
    config_path = Path('./config/config.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def test_ollama_connection():
    """测试Ollama连接"""
    print("=" * 60)
    print("🧪 测试Ollama连接")
    print("=" * 60)

    try:
        config = load_config()

        # 检查配置
        provider = config['llm']['provider'].lower()
        if provider != 'ollama':
            print(f"⚠️  当前配置使用的是 {provider}，不是ollama")
            print("   要测试Ollama，请在config.yaml中设置:")
            print("   llm:")
            print("     provider: ollama")
            print("     model: qwen3:4b-instruct  # 或其他本地模型")
            return False

        model_name = config['llm']['model']
        base_url = config['llm'].get('ollama_base_url', 'http://localhost:11434')

        print("📋 配置信息:")
        print(f"   模型: {model_name}")
        print(f"   服务地址: {base_url}")
        print(f"   温度: {config['llm']['temperature']}")

        # 创建Ollama实例
        print("\n🔗 连接Ollama服务...")
        llm = OllamaLLM(
            model=model_name,
            base_url=base_url,
            temperature=config['llm']['temperature']
        )

        # 测试基本调用
        print("💬 发送测试消息...")
        test_prompt = "请简单介绍一下你自己，限制在50字以内。"

        response = llm.invoke(test_prompt)

        print("✅ Ollama连接成功!")
        print(f"🤖 模型回复: {response}")

        # 验证回复质量
        if len(response.strip()) > 10:
            print("✅ 回复内容正常")
        else:
            print("⚠️  回复内容较短")

        return True

    except Exception as e:
        print(f"❌ Ollama测试失败: {str(e)}")

        print("\n🔧 故障排除:")
        print("1. 确保Ollama服务正在运行:")
        print("   ollama serve")
        print("")
        print("2. 确保模型已下载:")
        print(f"   ollama pull {config['llm']['model']}")
        print("")
        print("3. 检查服务地址:")
        print(f"   curl {config['llm']['ollama_base_url']}/api/tags")
        print("")
        print("4. 配置文件示例:")
        print("   llm:")
        print("     provider: ollama")
        print("     model: qwen3:4b-instruct")
        print("     ollama_base_url: http://localhost:11434")
        print("     temperature: 0.7")

        return False


def main():
    """主函数"""
    print("🔧 Ollama配置测试")
    print(f"工作目录: {os.getcwd()}")

    success = test_ollama_connection()

    if success:
        print("\n🎉 Ollama配置测试通过!")
        print("现在可以将config.yaml中的provider改为ollama来使用本地模型")
    else:
        print("\n💥 测试失败!")
        print("请检查Ollama安装和配置")


if __name__ == "__main__":
    main()
