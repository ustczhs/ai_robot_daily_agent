# 每日AI与机器人技术进展智能体 - 完整部署指南

本文档将指导您从零开始，在本地Ubuntu 22.04系统上部署并运行这个智能体，确保您能够按照步骤顺利实现每日自动生成技术日报的功能。

---

## 📋 目录

1. [系统要求](#系统要求)
2. [准备工作](#准备工作)
3. [详细部署步骤](#详细部署步骤)
4. [配置说明](#配置说明)
5. [运行与测试](#运行与测试)
6. [设置自动化调度](#设置自动化调度)
7. [常见问题与解决方案](#常见问题与解决方案)
8. [成本估算](#成本估算)
9. [优化建议](#优化建议)

---

## 系统要求

在开始之前，请确保您的系统满足以下要求。

| 项目 | 要求 |
|------|------|
| **操作系统** | Ubuntu 22.04 LTS (或其他Linux发行版) |
| **Python版本** | Python 3.11 或更高 |
| **内存** | 至少 4GB RAM |
| **存储空间** | 至少 10GB 可用空间 |
| **网络** | 稳定的互联网连接 |
| **API密钥** | OpenAI API Key (需要付费账户) |

---

## 准备工作

### 1. 获取阿里百炼 API 密钥

本项目使用阿里百炼（DashScope）API。

1. 访问 [阿里百炼控制台](https://dashscope.console.aliyun.com/)
2. 登录您的阿里云账户
3. 在左侧菜单选择 "API-KEY 管理"
4. 创建并获取您的 API-KEY
5. 复制并妥善保存您的 API 密钥（格式为 `sk-...`）

**重要提示**：请妥善保管您的API密钥，不要泄露给他人或提交到公开的代码仓库。

### 2. 安装系统依赖

在Ubuntu系统上，确保已安装必要的系统工具。

```bash
sudo apt update
sudo apt install python3.11 python3.11-venv git curl -y
```

验证Python版本：

```bash
python3.11 --version
```

应该输出类似 `Python 3.11.x` 的版本信息。

---

## 详细部署步骤

### 步骤1：获取项目代码

如果您已经有项目代码的压缩包，请解压到合适的目录。如果是从Git仓库克隆，执行：

```bash
cd ~
git clone <your-repo-url> ai_robot_daily_agent
cd ai_robot_daily_agent
```

*(注：请将`<your-repo-url>`替换为实际的仓库地址)*

如果您是从本文档所在的目录开始，项目文件应该已经存在于 `/home/ubuntu/ai_robot_daily_agent/` 目录下。

### 步骤2：创建 Conda 环境

我们使用 Conda 来管理项目环境。

```bash
conda create -n daily_agent python=3.11 -y
```

### 步骤3：激活 Conda 环境

```bash
conda activate daily_agent
```

激活后，您的终端提示符前面会出现 `(venv)` 标识，表示已进入虚拟环境。

### 步骤4：安装Python依赖

```bash
pip install -r requirements.txt
```

这个过程可能需要几分钟时间，取决于您的网络速度。安装完成后，所有必要的Python库都将被安装到虚拟环境中。

### 步骤5：配置API密钥

将您的OpenAI API密钥设置为环境变量。

**临时设置（仅当前终端会话有效）**：

```bash
export DASHSCOPE_API_KEY="sk-YourActualDashScopeKey"
```

**永久设置（推荐）**：

编辑您的shell配置文件（如 `~/.bashrc` 或 `~/.zshrc`）：

```bash
nano ~/.bashrc
```

在文件末尾添加以下行：

```bash
export DASHSCOPE_API_KEY="sk-YourActualDashScopeKey"
```

保存并退出（Ctrl+O, Enter, Ctrl+X），然后使配置生效：

```bash
source ~/.bashrc
```

验证环境变量是否设置成功：

```bash
echo $DASHSCOPE_API_KEY
```

应该输出您的API密钥。

### 步骤6：验证安装

运行测试脚本，确保所有依赖都已正确安装：

```bash
python test_run.py
```

您应该看到类似以下的输出：

```
================================================================================
🧪 测试数据生成
================================================================================

生成了 3 条测试数据：

1. [大语言模型与生成式AI] OpenAI发布GPT-5预览版，多模态能力大幅提升
   评分: 9.2/10

2. [机器人技术与具身智能] 波士顿动力推出新一代人形机器人Atlas 2.0
   评分: 8.8/10

3. [计算机视觉] Meta开源Segment Anything Model 2，视频分割精度提升40%
   评分: 8.5/10

✅ 测试数据准备完成
```

---

## 配置说明

项目的所有配置都集中在 `config/config.yaml` 文件中。您可以根据自己的需求进行调整。

### 核心配置项

#### 1. LLM配置

```yaml
llm:
  provider: "openai"
  model: "gpt-4.1-mini"  # 或 gpt-4.1-nano（更便宜）
  temperature: 0.7
  max_tokens: 4000
```

- `model`: 选择使用的模型。`gpt-4.1-mini` 性价比高，`gpt-4.1-nano` 更便宜但能力稍弱。
- `temperature`: 控制生成内容的随机性，0-1之间，越高越有创造性。

#### 2. 搜索关键词

```yaml
sources:
  keywords:
    - "AI breakthrough"
    - "artificial intelligence news"
    - "robotics technology"
    - "machine learning advancement"
    - "人工智能最新进展"
    - "机器人技术突破"
```

您可以添加或修改关键词，以调整信息采集的范围和方向。建议同时包含中英文关键词以扩大覆盖面。

#### 3. 内容过滤

```yaml
filtering:
  min_quality_score: 7.0  # 最低质量分数（0-10）
  max_age_hours: 48       # 最大内容年龄（小时）
  similarity_threshold: 0.85  # 去重相似度阈值
```

- `min_quality_score`: 只保留评分高于此值的内容。提高此值可以提高报告质量，但可能减少内容数量。
- `similarity_threshold`: 语义相似度阈值，0-1之间。越高则去重越严格。

#### 4. 技术分类

```yaml
categories:
  - "大语言模型与生成式AI"
  - "机器人技术与具身智能"
  - "计算机视觉"
  - "强化学习与决策智能"
  - "AI基础设施与工具"
  - "行业应用与产品"
  - "研究前沿与理论突破"
```

您可以根据自己关注的领域自定义分类标准。

---

## 运行与测试

### 手动运行

在虚拟环境激活的状态下，执行：

```bash
./main.py
```

您将看到类似以下的输出：

```
================================================================================
🤖 AI与机器人技术日报Agent 启动中...
================================================================================
2026-01-06 08:30:00,123 - __main__ - INFO - 配置加载成功
2026-01-06 08:30:00,124 - __main__ - INFO - 运行时间: 2026-01-06 08:30:00
2026-01-06 08:30:00,125 - agents.orchestrator - INFO - 开始执行日报生成流程...
2026-01-06 08:30:00,126 - agents.orchestrator - INFO - 📡 阶段1: 信息采集
2026-01-06 08:30:15,234 - agents.orchestrator - INFO -    收集到 45 条原始信息
2026-01-06 08:30:15,235 - agents.orchestrator - INFO - 🔍 阶段2: 内容分析与评分
...
```

整个流程可能需要5-15分钟，取决于收集到的信息量和API响应速度。

### 查看生成的报告

运行完成后，报告将保存在 `reports/` 目录下，文件名格式为 `ai_robot_daily_YYYYMMDD.md`。

```bash
ls -lh reports/
cat reports/ai_robot_daily_20260106.md
```

您也可以使用Markdown编辑器（如Typora、VS Code）打开报告文件，获得更好的阅读体验。

---

## 设置自动化调度

要实现每日自动运行，我们使用Linux的Cron服务。

### 步骤1：编辑Cron任务

```bash
crontab -e
```

如果是第一次使用，系统会提示您选择编辑器，建议选择 `nano`（输入对应的数字）。

### 步骤2：添加定时任务

在打开的文件末尾添加以下行：

```cron
0 8 * * * /home/ubuntu/ai_robot_daily_agent/run.sh >> /home/ubuntu/ai_robot_daily_agent/logs/cron.log 2>&1
```

这表示每天早上8点执行 `run.sh` 脚本，并将输出记录到 `logs/cron.log` 文件中。

**Cron时间格式说明**：

```
分钟 小时 日期 月份 星期 命令
0    8    *    *    *   /path/to/script
```

- `0 8 * * *`: 每天早上8:00
- `0 20 * * *`: 每天晚上8:00
- `0 8,20 * * *`: 每天早上8:00和晚上8:00

您可以根据需要调整时间。

### 步骤3：保存并退出

在nano编辑器中，按 `Ctrl+O` 保存，按 `Enter` 确认，然后按 `Ctrl+X` 退出。

### 步骤4：验证Cron任务

查看当前的Cron任务列表：

```bash
crontab -l
```

您应该看到刚才添加的任务。

### 步骤5：测试自动化脚本

不必等到第二天，您可以立即手动执行脚本来测试：

```bash
/home/ubuntu/ai_robot_daily_agent/run.sh
```

检查日志文件：

```bash
tail -f logs/cron.log
```

如果一切正常，您将看到Agent的运行日志。

---

## 常见问题与解决方案

### 问题1：`ModuleNotFoundError: No module named 'xxx'`

**原因**：依赖未正确安装，或未激活虚拟环境。

**解决方案**：

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### 问题2：`OpenAI API Error: Invalid API Key`

**原因**：API密钥未设置或设置错误。

**解决方案**：

1. 检查环境变量：`echo $DASHSCOPE_API_KEY`
2. 确保API密钥正确无误，格式为 `sk-...`
3. 重新设置环境变量并重启终端

### 问题3：搜索结果为空或很少

**原因**：Google搜索可能因为请求频率过高被限制，或关键词不够精准。

**解决方案**：

1. 在 `config/config.yaml` 中调整搜索关键词
2. 增加搜索延迟时间（修改 `agents/collector.py` 中的 `time.sleep(2)` 为更大的值）
3. 考虑使用付费搜索API（如Serper API、SerpAPI）

### 问题4：报告内容质量不高

**原因**：质量评分标准过低，或LLM模型能力不足。

**解决方案**：

1. 提高 `config/config.yaml` 中的 `min_quality_score` 值
2. 升级LLM模型（如从 `gpt-4.1-nano` 升级到 `gpt-4.1-mini`）
3. 优化 `agents/analyzer.py` 中的评分提示词

### 问题5：Cron任务未执行

**原因**：Cron服务未启动，或脚本路径错误。

**解决方案**：

1. 检查Cron服务状态：`sudo systemctl status cron`
2. 如果未运行，启动服务：`sudo systemctl start cron`
3. 确保 `run.sh` 中的路径与实际项目路径一致
4. 检查 `logs/cron.log` 文件查看错误信息

### 问题6：向量数据库报错

**原因**：ChromaDB版本兼容性问题，或数据库文件损坏。

**解决方案**：

1. 删除旧的数据库文件：`rm -rf data/chroma_db/`
2. 重新运行Agent，会自动创建新的数据库

---

## 成本估算

使用本智能体的主要成本来自OpenAI API调用。以下是基于每日运行一次的成本估算。

### API调用量估算（每日）

| 项目 | 调用次数 | 单价 | 成本 |
|------|---------|------|------|
| **搜索API** | 免费（自建爬虫） | $0 | $0 |
| **LLM分析** (gpt-4.1-mini) | 约50-100次 | $0.001/次 | $0.05-0.10 |
| **报告生成** (gpt-4.1-mini) | 约5-10次 | $0.001/次 | $0.005-0.01 |
| **嵌入向量** (text-embedding-3-small) | 约100-200次 | $0.00002/次 | $0.002-0.004 |

**每日总成本**：约 **$0.06-0.12**  
**每月总成本**：约 **$1.8-3.6**

### 成本优化建议

1. **使用更便宜的模型**：将 `gpt-4.1-mini` 替换为 `gpt-4.1-nano`，成本可降低约50%。
2. **减少分析次数**：提高 `min_quality_score` 阈值，减少需要深度分析的内容数量。
3. **使用本地模型**：使用Ollama运行本地开源模型（如Llama 3），完全免费，但需要GPU支持。
4. **批量处理**：修改代码，将多个分析请求合并为一次调用，减少API调用次数。

---

## 优化建议

### 1. 提升信息采集质量

- **增加信息源**：除了Google搜索，可以添加RSS订阅、Reddit API、Twitter API等。
- **使用付费搜索API**：如Serper API（免费2500次/月）或SerpAPI，获取更稳定的搜索结果。
- **爬取特定网站**：针对权威技术网站（如ArXiv、Hacker News）进行定向爬取。

### 2. 优化内容分析

- **微调评分标准**：根据实际使用反馈，调整 `agents/analyzer.py` 中的评分提示词。
- **增加多轮分析**：对高分内容进行二次深度分析，提取更多技术细节。
- **引入人工反馈**：定期人工标注报告质量，用于优化Agent行为。

### 3. 增强去重能力

- **扩大历史窗口**：将 `retention_days` 从30天扩大到60天或更长。
- **多维度去重**：除了语义相似度，还可以基于URL、标题进行初步去重。
- **聚类分析**：对相似内容进行聚类，只保留每个聚类中质量最高的一条。

### 4. 丰富报告内容

- **添加可视化**：使用Python的matplotlib或plotly生成技术趋势图表。
- **多语言支持**：生成中英文双语报告，扩大受众范围。
- **邮件推送**：使用SMTP服务，将报告自动发送到您的邮箱。
- **Web界面**：开发简单的Web界面，方便在线查看历史报告。

### 5. 使用本地模型

如果您有GPU资源，可以使用Ollama运行本地开源模型，完全免费。

**安装Ollama**：

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**下载模型**：

```bash
ollama pull llama3.1:8b
```

**修改配置**：

在 `config/config.yaml` 中修改LLM配置：

```yaml
llm:
  provider: "ollama"
  model: "llama3.1:8b"
  base_url: "http://localhost:11434"
```

然后修改 `agents/orchestrator.py`，使用 `ChatOllama` 替代 `ChatOpenAI`。

---

## 总结

通过本指南，您应该已经成功在本地Ubuntu系统上部署了这个智能体，并实现了每日自动生成AI与机器人技术日报的功能。

**核心优势**：

- ✅ **完全自动化**：无需人工干预，每天定时运行
- ✅ **高度可定制**：所有参数均可通过配置文件调整
- ✅ **成本可控**：月成本低于$5，可进一步优化至接近$0
- ✅ **质量保证**：多层过滤机制，确保内容的高价值和独特性
- ✅ **易于扩展**：基于Agent架构，可轻松添加新功能

如果您在部署过程中遇到任何问题，请参考"常见问题与解决方案"部分，或查看项目日志文件 `logs/agent.log` 获取详细的错误信息。

祝您使用愉快！🚀
