#!/bin/bash

# AI与机器人技术日报Agent - Cron执行脚本
# 用于定时任务自动运行

# 切换到项目目录
cd /home/zhs/code/ai_robot_daily_agent || exit 1

# 设置API密钥 (请替换为您的实际阿里百炼API密钥)
export DASHSCOPE_API_KEY="sk-5d894cdc85774350b6bb29d3be994c6e"

# 激活Conda环境
# 假设conda已安装并初始化
source $(conda info --base)/etc/profile.d/conda.sh
conda activate daily_agent

# 运行主程序
python main.py

# 退出环境
conda deactivate
