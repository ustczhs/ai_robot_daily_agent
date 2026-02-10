#!/usr/bin/env python3
"""
邮件发送模块 - 用于发送AI日报报告
"""

import os
import smtplib
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

logger = logging.getLogger(__name__)


class MailSender:
    """邮件发送器"""
    
    def __init__(self, smtp_server, smtp_port, username, password):
        """初始化邮件发送器
        
        Args:
            smtp_server: SMTP服务器地址
            smtp_port: SMTP服务器端口
            username: 邮箱用户名
            password: 邮箱密码/授权码
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        
    def send_email(self, recipients, subject, body, attachment_path=None):
        """发送邮件
        
        Args:
            recipients: 收件人列表
            subject: 邮件主题
            body: 邮件正文
            attachment_path: 附件路径（可选）
            
        Returns:
            bool: 发送成功返回True，失败返回False
        """
        try:
            # 创建邮件对象
            msg = MIMEMultipart()
            msg['From'] = self.username
            msg['To'] = ', '.join(recipients) if isinstance(recipients, list) else recipients
            msg['Subject'] = subject
            
            # 添加邮件正文
            msg.attach(MIMEText(body, 'html', 'utf-8'))
            
            # 添加附件（如果有）
            if attachment_path and Path(attachment_path).exists():
                self._add_attachment(msg, attachment_path)
            
            # 连接SMTP服务器并发送
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                # 启用TLS加密
                server.starttls()
                
                # 登录
                server.login(self.username, self.password)
                
                # 发送邮件
                server.send_message(msg)
                
            logger.info(f"邮件发送成功: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"邮件发送失败: {str(e)}")
            return False
    
    def _add_attachment(self, msg, file_path):
        """添加附件到邮件
        
        Args:
            msg: 邮件对象
            file_path: 附件文件路径
        """
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                logger.warning(f"附件文件不存在: {file_path}")
                return
                
            # 创建附件对象
            with open(file_path, 'rb') as f:
                attachment = MIMEBase('application', 'octet-stream')
                attachment.set_payload(f.read())
                
            # 编码附件
            encoders.encode_base64(attachment)
            
            # 添加附件头信息
            attachment.add_header(
                'Content-Disposition',
                f'attachment; filename="{file_path.name}"'
            )
            
            msg.attach(attachment)
            logger.info(f"附件添加成功: {file_path.name}")
            
        except Exception as e:
            logger.error(f"添加附件失败: {str(e)}")


def create_email_content(report_path):
    """创建邮件内容
    
    Args:
        report_path: 报告文件路径
        
    Returns:
        tuple: (subject, html_body)
    """
    try:
        # 从报告文件名提取日期
        report_file = Path(report_path).name
        date_str = report_file.replace('ai_robot_daily_', '').replace('.md', '')
        
        # 格式化日期
        if len(date_str) == 8:  # YYYYMMDD格式
            formatted_date = f"{date_str[:4]}年{date_str[4:6]}月{date_str[6:]}日"
        else:
            formatted_date = date_str
            
        # 邮件主题
        subject = f"AI与机器人技术日报 - {formatted_date}"
        
        # 邮件正文（HTML格式）
        html_body = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; line-height: 1.6; margin: 0; padding: 20px; background-color: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ text-align: center; margin-bottom: 30px; padding-bottom: 20px; border-bottom: 2px solid #007acc; }}
                .header h1 {{ color: #007acc; margin: 0; font-size: 24px; }}
                .header p {{ color: #666; margin: 10px 0 0 0; }}
                .content {{ margin: 20px 0; }}
                .highlight {{ background: #e8f4fd; padding: 15px; border-left: 4px solid #007acc; margin: 20px 0; border-radius: 5px; }}
                .footer {{ text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; color: #666; font-size: 14px; }}
                .button {{ display: inline-block; padding: 12px 24px; background: #007acc; color: white; text-decoration: none; border-radius: 5px; margin: 10px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🤖 AI与机器人技术日报</h1>
                    <p>{formatted_date}</p>
                </div>
                
                <div class="content">
                    <p>您好！</p>
                    
                    <p>今日AI与机器人技术日报已生成完成，请查收附件中的详细报告，也可访问 <a href="http://172.16.40.98:5000/" target="_blank" style="color: #007acc; text-decoration: none;">http://172.16.40.98:5000/</a> 在线查看。</p>
                    
                    <div class="highlight">
                        <strong>📊 报告内容概览：</strong>
                        <ul>
                            <li>最新AI技术进展与突破</li>
                            <li>机器人技术创新与应用</li>
                            <li>行业动态与市场分析</li>
                            <li>前沿研究论文解读</li>
                            <li>趋势预测与发展方向</li>
                        </ul>
                    </div>
                    
                    <p>本报告由AI自动收集、分析、整理生成，旨在为您提供及时、准确的技术资讯。</p>
                    
                    <p>如有任何问题或建议，欢迎回复此邮件。</p>
                </div>
                
                <div class="footer">
                    <p>🚀 AI与机器人技术日报 | 自动生成于 {datetime.now().strftime('%Y年%m月%d日 %H:%M')}</p>
                    <p>本邮件由AI日报系统自动发送</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return subject, html_body
        
    except Exception as e:
        logger.error(f"创建邮件内容失败: {str(e)}")
        # 返回默认内容
        return "AI与机器人技术日报", "您好，今日AI与机器人技术日报已生成完成，请查收附件。"


def send_daily_report(report_path, email_config):
    """发送日报报告邮件
    
    Args:
        report_path: 报告文件路径
        email_config: 邮件配置字典
        
    Returns:
        bool: 发送成功返回True，失败返回False
    """
    try:
        # 检查邮件功能是否启用
        if not email_config.get('enabled', False):
            logger.info("邮件功能未启用，跳过发送")
            return True
            
        # 获取必要配置
        smtp_server = email_config.get('smtp_server')
        smtp_port = email_config.get('smtp_port', 587)
        username = email_config.get('username')
        password_env = email_config.get('password_env', 'EMAIL_PASSWORD')
        recipients = email_config.get('recipients', [])
        
        if not all([smtp_server, username, recipients]):
            logger.error("邮件配置不完整")
            return False
            
        # 从环境变量获取密码
        password = os.getenv(password_env)
        if not password:
            logger.error(f"未找到环境变量: {password_env}")
            return False
            
        # 创建邮件发送器
        mailer = MailSender(smtp_server, smtp_port, username, password)
        
        # 创建邮件内容
        subject, body = create_email_content(report_path)
        
        # 发送邮件
        success = mailer.send_email(recipients, subject, body, report_path)
        
        if success:
            logger.info(f"日报邮件发送成功: {len(recipients)} 个收件人")
        else:
            logger.error("日报邮件发送失败")
            
        return success
        
    except Exception as e:
        logger.error(f"发送日报邮件失败: {str(e)}")
        return False


# 测试函数
def test_email_config():
    """测试邮件配置"""
    try:
        # 检查环境变量
        password = os.getenv('EMAIL_PASSWORD')
        if not password:
            print("❌ 未设置 EMAIL_PASSWORD 环境变量")
            print("   请执行: export EMAIL_PASSWORD='你的邮箱授权码'")
            return False
            
        print("✅ 邮件配置检查通过")
        return True
        
    except Exception as e:
        print(f"❌ 配置检查失败: {str(e)}")
        return False


if __name__ == "__main__":
    # 测试模块
    print("邮件发送模块测试")
    test_email_config()