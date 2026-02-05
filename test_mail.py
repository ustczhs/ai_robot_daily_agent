#!/usr/bin/env python3
"""
完整邮件发送测试用例
包含详细的测试步骤和错误诊断
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

def test_smtp_connection():
    """单独测试SMTP连接"""
    print("=" * 50)
    print("🔗 SMTP连接测试")
    print("=" * 50)
    
    try:
        import yaml
        with open("./config/config.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
        email_config = config.get('email', {})
        
        if not email_config.get('enabled', False):
            print("⚠️  邮件功能未启用")
            return False
            
        smtp_server = email_config.get('smtp_server')
        smtp_port = email_config.get('smtp_port', 587)
        username = email_config.get('username')
        password = os.getenv('EMAIL_PASSWORD')
        
        if not all([smtp_server, username, password]):
            print("❌ 配置信息不完整")
            return False
            
        print(f"服务器: {smtp_server}:{smtp_port}")
        print(f"用户名: {username}")
        
        # 测试SMTP连接
        import smtplib
        
        print("\n📡 正在连接SMTP服务器...")
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            print("✅ SMTP连接成功")
            
            # 测试TLS
            try:
                server.starttls()
                print("✅ TLS加密启用成功")
            except Exception as e:
                print(f"⚠️  TLS启用失败: {e}")
            
            # 测试登录
            try:
                server.login(username, password)
                print("✅ SMTP登录成功")
                return True
            except Exception as e:
                print(f"❌ SMTP登录失败: {e}")
                print("   请检查用户名和密码")
                return False
                
    except Exception as e:
        print(f"❌ SMTP测试失败: {str(e)}")
        return False

def create_test_report():
    """创建测试报告文件"""
    print("\n" + "=" * 50)
    print("📝 创建测试报告")
    print("=" * 50)
    
    test_report_path = "./reports/test_email_report.md"
    
    test_content = f"""# AI与机器人技术日报 - 邮件测试报告

**生成时间**: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}
**测试目的**: 验证邮件发送功能

## 📧 邮件发送测试

这是一份专门用于测试邮件发送功能的报告文件。

### 测试内容
- ✅ 报告文件生成
- ✅ 邮件内容构建
- ✅ 附件添加功能
- ✅ SMTP服务器连接
- ✅ 邮件发送功能

### 测试信息
- **测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **报告文件**: {Path(test_report_path).name}
- **文件大小**: 约 {len(test_content) / 1024:.1f} KB

### 功能验证
此报告用于验证以下功能：
1. 邮件发送模块是否正确加载
2. 报告文件能否作为附件成功发送
3. 邮件内容格式是否正确
4. SMTP服务器连接是否稳定

---
*本报告由AI日报系统自动生成，专门用于邮件功能测试*
"""
    
    try:
        # 确保报告目录存在
        Path("./reports").mkdir(exist_ok=True)
        
        # 写入测试报告
        with open(test_report_path, 'w', encoding='utf-8') as f:
            f.write(test_content)
            
        print(f"✅ 测试报告创建成功: {test_report_path}")
        print(f"✅ 文件大小: {len(test_content) / 1024:.1f} KB")
        return test_report_path
        
    except Exception as e:
        print(f"❌ 创建测试报告失败: {str(e)}")
        return None

def main():
    """主测试函数"""
    print("🚀 AI日报邮件发送功能测试")
    print("=" * 60)
    
    # 显示配置信息
    print("\n📋 当前配置:")
    try:
        import yaml
        with open("./config/config.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
        email_config = config.get('email', {})
        print(f"   SMTP服务器: {email_config.get('smtp_server', '未配置')}")
        print(f"   用户名: {email_config.get('username', '未配置')}")
        print(f"   收件人: {email_config.get('recipients', [])}")
        print(f"   邮件功能: {'启用' if email_config.get('enabled', False) else '禁用'}")
        
    except Exception as e:
        print(f"   读取配置失败: {e}")
    
    # 测试步骤
    print("\n" + "=" * 40)
    print("请选择测试项目:")
    print("1. 完整邮件发送测试")
    print("2. SMTP连接测试")
    print("3. 创建测试报告")
    print("4. 退出")
    print("=" * 40)
    
    choice = input("\n请输入选项 (1-4): ").strip()
    
    if choice == '1':
        # 完整测试
        print("\n1️⃣ 检查环境变量...")
        password = os.getenv('EMAIL_PASSWORD')
        if not password:
            print("❌ 未设置 EMAIL_PASSWORD 环境变量")
            print("   请执行: export EMAIL_PASSWORD='你的邮箱密码'")
            return
            
        print("✅ 环境变量已设置")
        
        # 查找最新报告
        reports_dir = Path("./reports")
        report_files = list(reports_dir.glob("ai_robot_daily_*.md"))
        if not report_files:
            print("❌ 未找到报告文件")
            return
            
        latest_report = max(report_files, key=lambda x: x.stat().st_mtime)
        print(f"📄 使用报告: {latest_report.name}")
        
        # 发送邮件
        print("📧 正在发送邮件...")
        from utils.mailer import send_daily_report
        
        success = send_daily_report(str(latest_report), email_config)
        
        if success:
            print("✅ 邮件发送成功！")
        else:
            print("❌ 邮件发送失败")
            
    elif choice == '2':
        test_smtp_connection()
        
    elif choice == '3':
        create_test_report()
        
    elif choice == '4':
        print("\n👋 测试结束，再见！")
        
    else:
        print("\n❌ 无效选项")

if __name__ == "__main__":
    main()
