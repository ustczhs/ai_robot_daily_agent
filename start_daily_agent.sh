#!/usr/bin/env bash

# ==================== 显式加载 conda 环境（脚本自身先加载，确保能找到 conda） ====================
if [ -f ~/miniconda3/etc/profile.d/conda.sh ]; then
    . ~/miniconda3/etc/profile.d/conda.sh
elif [ -f ~/anaconda3/etc/profile.d/conda.sh ]; then
    . ~/anaconda3/etc/profile.d/conda.sh
else
    echo "错误：找不到 conda.sh，请检查 Miniconda/Anaconda 安装路径"
    exit 1
fi

conda activate daily_agent || { echo "conda activate daily_agent 失败"; exit 1; }

# ==================== 配置区 ====================
PROJECT_DIR="$HOME/code/ai_robot_daily_agent"
ENV_NAME="daily_agent"
SESSION_NAME="daily_agent"
LOG_FILE="$HOME/daily_agent_startup.log"

# ==================== 清理旧会话和端口 ====================
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 清理旧 tmux 会话和 5000 端口" >> "$LOG_FILE"

tmux has-session -t "$SESSION_NAME" 2>/dev/null && tmux kill-session -t "$SESSION_NAME"

# 杀掉占用 5000 端口的进程（非 sudo 版，如果进程是你用户的）
lsof -ti :5000 | xargs -r kill -9 2>/dev/null || true

# ==================== 不要随意修改下面 ====================
if [ ! -d "$PROJECT_DIR" ]; then
    echo "错误：项目目录不存在 → $PROJECT_DIR" >> "$LOG_FILE"
    exit 1
fi

# 新建 tmux 会话
tmux new-session -d -s "$SESSION_NAME"

# 窗口 0 → main.py
tmux rename-window -t "$SESSION_NAME":0 "main"
tmux send-keys -t "$SESSION_NAME":0 "bash -c '. ~/.bashrc && conda activate ${ENV_NAME} && export https_proxy=http://127.0.0.1:7897 && export http_proxy=http://127.0.0.1:7897 && export all_proxy=socks5://127.0.0.1:7897 && cd ${PROJECT_DIR} && python main.py'" C-m

# 新建窗口 1 → gunicorn
tmux new-window -t "$SESSION_NAME":1 -n "web"
tmux send-keys -t "$SESSION_NAME":1 "bash -c '. ~/.bashrc && conda activate ${ENV_NAME} && export https_proxy=http://127.0.0.1:7897 && export http_proxy=http://127.0.0.1:7897 && export all_proxy=socks5://127.0.0.1:7897 && cd ${PROJECT_DIR} && gunicorn --bind 0.0.0.0:5000 web:app'" C-m

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 启动完成！会话: ${SESSION_NAME}" >> "$LOG_FILE"
echo "查看方式：tmux a -t ${SESSION_NAME}"
echo "日志：tail -f ${LOG_FILE}"
