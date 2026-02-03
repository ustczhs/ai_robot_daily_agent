#!/usr/bin/env python3
"""
AI日报Web服务 - 云端部署版本
将日报报告发布到Web浏览器查看
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, send_from_directory, abort
import markdown2

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 配置路径
REPORTS_DIR = Path('./reports')
STATIC_DIR = Path('./static')

@app.route('/')
def index():
    """首页：显示最新日报报告"""
    try:
        # 获取最新的报告文件
        if REPORTS_DIR.exists():
            report_files = list(REPORTS_DIR.glob('ai_robot_daily_*.md'))
            if report_files:
                # 按文件名排序，取最新的
                latest_report = max(report_files, key=lambda x: x.stat().st_mtime)

                # 读取并转换为HTML
                with open(latest_report, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()

                # 转换为HTML
                html_content = markdown2.markdown(
                    markdown_content,
                    extras=['tables', 'fenced-code-blocks', 'toc']
                )

                report_date = latest_report.stem.replace('ai_robot_daily_', '')
                if len(report_date) == 8:  # 格式化日期显示
                    report_date = f"{report_date[:4]}年{report_date[4:6]}月{report_date[6:]}日"

                return render_template('index.html',
                                     content=html_content,
                                     report_date=report_date,
                                     last_updated=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            else:
                return render_template('index.html',
                                     content="<h3>暂无报告</h3><p>还没有生成日报报告，请稍后查看。</p>",
                                     report_date="暂无",
                                     last_updated=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        else:
            return render_template('index.html',
                                 content="<h3>服务配置中</h3><p>报告目录不存在，请联系管理员。</p>",
                                 report_date="暂无",
                                 last_updated=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    except Exception as e:
        logger.error(f"加载最新报告失败: {str(e)}")
        return render_template('index.html',
                             content=f"<h3>加载失败</h3><p>错误信息: {str(e)}</p>",
                             report_date="错误",
                             last_updated=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

@app.route('/reports')
def reports():
    """历史报告列表页面"""
    try:
        report_list = []

        if REPORTS_DIR.exists():
            report_files = list(REPORTS_DIR.glob('ai_robot_daily_*.md'))

            for report_file in sorted(report_files, reverse=True):
                # 从文件名提取日期
                filename = report_file.stem
                date_str = filename.replace('ai_robot_daily_', '')

                # 格式化日期显示
                if len(date_str) == 8:  # YYYYMMDD格式
                    display_date = f"{date_str[:4]}年{date_str[4:6]}月{date_str[6:]}日"
                    sort_key = date_str
                else:
                    display_date = date_str
                    sort_key = date_str

                # 获取文件大小和修改时间
                stat = report_file.stat()
                file_size = f"{stat.st_size / 1024:.1f} KB"
                modified_time = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')

                report_list.append({
                    'filename': filename,
                    'display_date': display_date,
                    'sort_key': sort_key,
                    'file_size': file_size,
                    'modified_time': modified_time,
                    'url': f"/report/{filename}"
                })

        return render_template('reports.html', reports=report_list)

    except Exception as e:
        logger.error(f"加载报告列表失败: {str(e)}")
        return render_template('reports.html', reports=[], error=str(e))

@app.route('/report/<filename>')
def view_report(filename):
    """查看特定报告"""
    try:
        # 安全检查：只允许查看以ai_robot_daily_开头的文件
        if not filename.startswith('ai_robot_daily_') or '..' in filename:
            abort(404)

        report_path = REPORTS_DIR / f"{filename}.md"

        if not report_path.exists():
            abort(404)

        # 读取并转换为HTML
        with open(report_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()

        html_content = markdown2.markdown(
            markdown_content,
            extras=['tables', 'fenced-code-blocks', 'toc']
        )

        # 从文件名提取日期
        date_str = filename.replace('ai_robot_daily_', '')
        if len(date_str) == 8:
            display_date = f"{date_str[:4]}年{date_str[4:6]}月{date_str[6:]}日"
        else:
            display_date = date_str

        return render_template('report.html',
                             content=html_content,
                             report_date=display_date,
                             filename=filename)

    except Exception as e:
        logger.error(f"加载报告 {filename} 失败: {str(e)}")
        return render_template('error.html', error=str(e)), 500

@app.route('/api/latest')
def api_latest():
    """API: 获取最新报告信息"""
    try:
        if REPORTS_DIR.exists():
            report_files = list(REPORTS_DIR.glob('ai_robot_daily_*.md'))
            if report_files:
                latest_report = max(report_files, key=lambda x: x.stat().st_mtime)
                filename = latest_report.stem

                return {
                    'success': True,
                    'latest_report': filename,
                    'url': f"/report/{filename}",
                    'last_updated': datetime.fromtimestamp(latest_report.stat().st_mtime).isoformat()
                }
        return {'success': False, 'message': '暂无报告'}

    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.route('/health')
def health():
    """健康检查"""
    return {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0'
    }

@app.route('/static/<path:filename>')
def static_files(filename):
    """静态文件服务"""
    return send_from_directory(STATIC_DIR, filename)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template('error.html', error="服务器内部错误"), 500

def create_templates_and_static():
    """创建必要的模板和静态文件目录"""
    # 创建模板目录
    templates_dir = Path('./templates')
    templates_dir.mkdir(exist_ok=True)

    # 创建静态文件目录
    static_dir = Path('./static')
    static_dir.mkdir(exist_ok=True)

    css_dir = static_dir / 'css'
    css_dir.mkdir(exist_ok=True)

    js_dir = static_dir / 'js'
    js_dir.mkdir(exist_ok=True)

    logger.info("模板和静态文件目录创建完成")

if __name__ == '__main__':
    # 开发环境运行
    create_templates_and_static()

    # 从环境变量获取端口，默认5000
    port = int(os.getenv('PORT', 5000))
    host = os.getenv('HOST', '0.0.0.0')

    logger.info(f"启动AI日报Web服务: http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
