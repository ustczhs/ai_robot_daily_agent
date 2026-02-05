#!/usr/bin/env python3
"""
AI与机器人技术日报Agent - 主入口
每日自动收集、分析、生成技术进展报告
"""

import os
import sys
import yaml
import logging
from datetime import datetime
from pathlib import Path

from agents.orchestrator import DailyReportOrchestrator


def setup_logging(config: dict) -> logging.Logger:
    """配置日志系统"""
    log_config = config.get('logging', {})
    log_file = log_config.get('file', './logs/agent.log')
    log_level = log_config.get('level', 'INFO')
    
    # 确保日志目录存在
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    
    # 配置日志格式
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    return logging.getLogger(__name__)


def load_config(config_path: str = './config/config.yaml') -> dict:
    """加载配置文件"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def main():
    """主函数"""
    print("=" * 80)
    print("🤖 AI与机器人技术日报Agent 启动中...")
    print("=" * 80)
    
    try:
        # 加载配置
        config = load_config()
        logger = setup_logging(config)
        
        logger.info("配置加载成功")
        logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 检查API密钥
        api_key = os.getenv('DASHSCOPE_API_KEY') or os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.error("未找到 DASHSCOPE_API_KEY 或 OPENAI_API_KEY 环境变量")
            print("\n❌ 错误: 请设置 DASHSCOPE_API_KEY 环境变量")
            print("   export DASHSCOPE_API_KEY='your-dashscope-api-key'")
            sys.exit(1)
        
        # 创建并运行编排器
        orchestrator = DailyReportOrchestrator(config)
        logger.info("开始执行日报生成流程...")
        
        report_path = orchestrator.run()
        
        print("\n" + "=" * 80)
        print("✅ 报告生成成功!")
        print(f"📄 报告路径: {report_path}")
        
        # 自动发送邮件（如果启用）
        try:
            email_config = config.get('email', {})
            if email_config.get('enabled', False):
                print("📧 正在发送邮件通知...")
                from utils.mailer import send_daily_report
                
                email_success = send_daily_report(report_path, email_config)
                if email_success:
                    print("✅ 邮件发送成功!")
                else:
                    print("❌ 邮件发送失败，请检查配置")
            else:
                print("📧 邮件推送未启用（可在config.yaml中配置）")
        except Exception as e:
            print(f"⚠️  邮件发送异常: {str(e)}")
            logger.error(f"邮件发送失败: {str(e)}")
        
        print("=" * 80)
        
        logger.info(f"报告已保存至: {report_path}")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断执行")
        sys.exit(0)
    except Exception as e:
        logger.error(f"执行失败: {str(e)}", exc_info=True)
        print(f"\n❌ 错误: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()