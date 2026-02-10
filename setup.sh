#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

clear
echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}   Termux Bot Manager (PM2 Enabled)    ${NC}"
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
    echo -e "\n${BLUE}[1/4] 检查代码更新...${NC}"
    # 尝试拉取更新，如果有本地冲突则忽略，优先保证本地运行
    if git pull | grep -q "Already up to date"; then
        echo "  当前已是最新版本。"
    else
        echo -e "  ${GREEN}✔ 代码已更新${NC}"
    fi
else
    echo -e "\n${BLUE}[1/4] 非 Git 仓库，跳过更新检查${NC}"
fi

# 2. 系统依赖检测
echo -e "\n${BLUE}[2/4] 检查系统环境...${NC}"
# 这里的 update 比较耗时，如果为了极速体验可以注释掉，但为了稳健建议保留
# pkg update -y 

check_install "git"
check_install "python"
check_install "nodejs" "node" # PM2 需要 Node.js

# 3. Python 依赖
echo -e "\n${BLUE}[3/4] 检查 Python 库...${NC}"
# 升级 pip (可选，为了速度暂注释)
# pip install --upgrade pip > /dev/null 2>&1

if [ ! -f "requirements.txt" ]; then
    echo "创建默认 requirements.txt..."
    echo "python-telegram-bot==20.8" > requirements.txt
fi

# 安静模式安装依赖，如果已安装会自动快速跳过
pip install -r requirements.txt
echo -e "  ${GREEN}✔ Python 依赖就绪${NC}"

# 4. PM2 进程管理
echo -e "\n${BLUE}[4/4] 配置后台进程管理 (PM2)...${NC}"

# 检查 PM2
if ! command -v pm2 &> /dev/null; then
    echo -e "${YELLOW}正在安装 PM2...${NC}"
    npm install -g pm2
    echo -e "  ${GREEN}✔ PM2 安装完成${NC}"
else
    echo -e "  ${GREEN}✔ PM2 已安装${NC}"
fi

# 赋予执行权限
chmod +x bot.py

APP_NAME="termux-bot"
SCRIPT_FILE="bot.py"

# 检查 PM2 中是否已存在该任务
if pm2 describe "$APP_NAME" > /dev/null 2>&1; then
    echo -e "重启机器人进程..."
    pm2 restart "$APP_NAME"
else
    echo -e "首次启动机器人..."
    # 使用 python 解释器启动
    pm2 start "$SCRIPT_FILE" --name "$APP_NAME" --interpreter python
fi

# 保存当前进程列表
pm2 save --force > /dev/null

echo -e "\n${BLUE}=======================================${NC}"
echo -e "       ${GREEN}🚀 机器人已在后台运行！${NC}"
echo -e "${BLUE}=======================================${NC}"
echo -e "常用命令："
echo -e "  👀 查看日志:   ${YELLOW}pm2 log $APP_NAME${NC}"
echo -e "  🛑 停止运行:   ${YELLOW}pm2 stop $APP_NAME${NC}"
echo -e "  🔄 重启服务:   ${YELLOW}pm2 restart $APP_NAME${NC}"
echo -e "  📋 进程列表:   ${YELLOW}pm2 list${NC}"
echo -e "${BLUE}=======================================${NC}"

# 自动展示 3 秒日志确认运行状态
echo -e "正在加载日志预览 (3秒)..."
timeout 3s pm2 log "$APP_NAME" --nostream --lines 5
