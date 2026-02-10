#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

clear
echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}   Termux Bot: Alist + FFmpeg Stream   ${NC}"
echo -e "${BLUE}=======================================${NC}"

# 函数：检查并安装软件包
check_install() {
    pkg_name=$1
    bin_name=$2
    if [ -z "$bin_name" ]; then bin_name=$pkg_name; fi

    if ! command -v "$bin_name" &> /dev/null; then
        echo -e "${YELLOW}正在安装 $pkg_name...${NC}"
        pkg install "$pkg_name" -y
    else
        echo -e "  ${GREEN}✔${NC} $pkg_name 已安装"
    fi
}

# 1. 自动更新 (Git Pull)
if [ -d ".git" ]; then
    echo -e "\n${BLUE}[1/5] 检查代码更新...${NC}"
    if git pull | grep -q "Already up to date"; then
        echo "  当前已是最新版本。"
    else
        echo -e "  ${GREEN}✔ 代码已更新${NC}"
    fi
else
    echo -e "\n${BLUE}[1/5] 非 Git 仓库，跳过更新检查${NC}"
fi

# 2. 系统依赖检测
echo -e "\n${BLUE}[2/5] 检查系统环境...${NC}"
check_install "git"
check_install "python"
check_install "nodejs" "node" # PM2 需要 Node.js
check_install "ffmpeg"        # 推流核心
check_install "alist"         # 网盘挂载

# 3. Python 依赖
echo -e "\n${BLUE}[3/5] 检查 Python 库...${NC}"
if [ ! -f "requirements.txt" ]; then
    echo "创建默认 requirements.txt..."
    echo -e "python-telegram-bot==20.8\npsutil==5.9.8\nrequests==2.31.0" > requirements.txt
fi

# 安静模式安装依赖
pip install -r requirements.txt
echo -e "  ${GREEN}✔ Python 依赖就绪${NC}"

# 4. 初始化 Alist (如果未配置)
echo -e "\n${BLUE}[4/5] 检查 Alist 配置...${NC}"
if [ ! -d "$HOME/.config/alist" ]; then
    echo -e "${YELLOW}首次运行 Alist 以生成配置文件...${NC}"
    # 运行一次 version 命令通常可以初始化目录，或者短暂启动
    timeout 5s alist server > /dev/null 2>&1
    echo -e "  ${GREEN}✔ Alist 初始化完成${NC}"
else
    echo -e "  ${GREEN}✔ Alist 配置文件已存在${NC}"
fi

# 5. PM2 进程管理
echo -e "\n${BLUE}[5/5] 配置后台进程管理 (PM2)...${NC}"

if ! command -v pm2 &> /dev/null; then
    echo -e "${YELLOW}正在安装 PM2...${NC}"
    npm install -g pm2
    echo -e "  ${GREEN}✔ PM2 安装完成${NC}"
else
    echo -e "  ${GREEN}✔ PM2 已安装${NC}"
fi

chmod +x bot.py

APP_NAME="termux-bot"
SCRIPT_FILE="bot.py"

# 检查 PM2
if pm2 describe "$APP_NAME" > /dev/null 2>&1; then
    echo -e "重启机器人进程..."
    pm2 restart "$APP_NAME"
else
    echo -e "首次启动机器人..."
    pm2 start "$SCRIPT_FILE" --name "$APP_NAME" --interpreter python
fi

pm2 save --force > /dev/null

echo -e "\n${BLUE}=======================================${NC}"
echo -e "       ${GREEN}🚀 机器人已启动！${NC}"
echo -e "${BLUE}=======================================${NC}"
echo -e "使用说明："
echo -e "1. 发送 /start 给机器人"
echo -e "2. 发送 /alist 管理网盘服务"
echo -e "3. 发送 /stream 开始推流直播"
echo -e "${BLUE}=======================================${NC}"

echo -e "正在加载日志预览 (3秒)..."
timeout 3s pm2 log "$APP_NAME" --nostream --lines 5
