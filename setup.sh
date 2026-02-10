#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

clear
echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}    Termux Bot 一键启动脚本    ${NC}"
echo -e "${BLUE}=======================================${NC}"

# 1. 检测并安装 Python
echo -e "\n${GREEN}[1/3] 检测 Python 环境...${NC}"
if ! command -v python &> /dev/null; then
    echo "正在安装 Python..."
    pkg update -y
    pkg install python -y
    pkg install python-pip -y
else
    echo "Python 已安装。"
fi

# 2. 安装依赖
echo -e "\n${GREEN}[2/3] 安装依赖库...${NC}"
# 升级 pip 以避免旧版本问题
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "正在生成 requirements.txt..."
    echo "python-telegram-bot==20.8" > requirements.txt
    pip install -r requirements.txt
fi

# 3. 赋予权限并启动
echo -e "\n${GREEN}[3/3] 启动机器人...${NC}"

# 关键：在这里给 bot.py 添加执行权限
chmod +x bot.py

echo -e "正在运行..."
echo -e "---------------------------------------"
python bot.py
