# AI日报Web服务部署指南

## 📋 概述

AI日报系统现在支持Web服务，可以通过浏览器查看日报报告。本指南介绍如何部署Web服务到各种云平台。

## 🚀 本地测试

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 运行Web服务
```bash
# 开发模式
python web.py

# 或生产模式
gunicorn --bind 0.0.0.0:5000 web:app
```

### 3. 访问服务
打开浏览器访问：`http://localhost:5000`

## ☁️ 云平台部署

### 方案1：Railway（推荐）

Railway 是现代化的云平台，Python支持良好。

#### 部署步骤：
1. 注册Railway账户：https://railway.app
2. 连接GitHub仓库
3. Railway会自动检测并部署
4. 设置环境变量（如果需要）

#### 环境变量设置：
```bash
# 可选：如果需要代理
HTTP_PROXY=http://your-proxy:port
HTTPS_PROXY=http://your-proxy:port

# 可选：如果使用远程LLM
DASHSCOPE_API_KEY=your-api-key
OPENAI_API_KEY=your-api-key
```

### 方案2：Vercel

Vercel 支持Python部署，但有冷启动问题。

#### 部署步骤：
1. 注册Vercel账户：https://vercel.com
2. 安装Vercel CLI：`npm install -g vercel`
3. 部署命令：
```bash
vercel --prod
```

### 方案3：Heroku

Heroku 是传统云平台，稳定可靠。

#### 部署步骤：
1. 注册Heroku账户：https://heroku.com
2. 安装Heroku CLI
3. 创建应用：
```bash
heroku create your-app-name
git push heroku main
```

### 方案4：阿里云服务器

适合国内用户，访问速度快。

#### 部署步骤：
1. 购买阿里云轻量应用服务器
2. 配置Python环境
3. 上传代码并运行：
```bash
# 安装依赖
pip install -r requirements.txt

# 运行服务
gunicorn --bind 0.0.0.0:80 web:app
```

## 🔧 配置说明

### 必需文件
- `web.py` - Flask应用主文件
- `templates/` - HTML模板目录
- `static/` - 静态文件目录（CSS/JS）
- `requirements.txt` - Python依赖
- `Procfile` - Heroku部署配置

### 环境变量
```bash
# 服务器配置
PORT=5000                    # 服务端口
HOST=0.0.0.0               # 绑定地址

# 可选：代理设置
HTTP_PROXY=http://proxy:port
HTTPS_PROXY=http://proxy:port

# 可选：API密钥
DASHSCOPE_API_KEY=your-key
OPENAI_API_KEY=your-key
```

## 🌟 功能特性

### 页面功能
- **首页** (`/`): 显示最新日报报告
- **历史报告** (`/reports`): 列出所有历史报告
- **单个报告** (`/report/filename`): 查看特定报告
- **API接口** (`/api/latest`): 获取最新报告信息
- **健康检查** (`/health`): 系统状态检查

### 界面特性
- 📱 **响应式设计**: 支持手机/PC访问
- 🎨 **美观界面**: Bootstrap + 自定义样式
- 📖 **Markdown渲染**: 支持表格、代码块、TOC
- 🧭 **智能导航**: 自动生成目录和章节导航
- ⚡ **快速加载**: CDN加速的静态资源

## 🔍 故障排除

### 常见问题

#### 1. 报告不显示
- 检查`reports/`目录是否存在报告文件
- 确认文件格式为`ai_robot_daily_YYYYMMDD.md`

#### 2. 部署失败
- 检查Python版本（推荐3.8+）
- 确认所有依赖已安装
- 查看日志文件：`logs/agent.log`

#### 3. 访问超时
- 检查网络连接
- 确认端口配置正确
- 查看防火墙设置

### 日志查看
```bash
# 查看应用日志
tail -f logs/agent.log

# Railway日志
railway logs

# Heroku日志
heroku logs --tail
```

## 📞 技术支持

如果遇到部署问题，请检查：
1. Python版本和依赖安装
2. 环境变量配置
3. 网络连接和防火墙
4. 磁盘空间和内存使用

## 🎯 使用建议

### 生产环境建议
- 使用Railway或阿里云服务器
- 设置定时任务自动生成报告
- 配置监控和告警
- 定期备份报告数据

### 开发环境建议
- 本地开发使用`python web.py`
- 使用版本控制管理代码
- 定期更新依赖包

---

*最后更新: 2026年01月20日*
