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

# 1. 手动/首次运行时的更新检查 (Updater 脚本也会做这个，但保留作为手动入口)
if [ -d ".git" ]; then
    echo -e "\n${BLUE}[1/6] 检查代码更新 (手动触发)...${NC}"
    # 简单的拉取尝试，不处理复杂冲突，复杂逻辑交给 auto_update.py
    if git pull --rebase 2>&1 | grep -q "Already up to date"; then
        echo "  当前已是最新版本。"
    else
        echo -e "  ${GREEN}✔ 代码已更新${NC}"
    fi
else
    echo -e "\n${BLUE}[1/6] 非 Git 仓库，跳过更新检查${NC}"
fi

# 2. 系统依赖检测
echo -e "\n${BLUE}[2/6] 检查系统环境...${NC}"
check_install "git"
check_install "python"
check_install "nodejs" "node" # PM2 需要 Node.js
check_install "ffmpeg"        # 推流核心
check_install "alist"         # 网盘挂载

# 3. Python 依赖
echo -e "\n${BLUE}[3/6] 检查 Python 库...${NC}"
if [ ! -f "requirements.txt" ]; then
    echo "创建默认 requirements.txt..."
    echo -e "python-telegram-bot==20.8\npsutil==5.9.8\nrequests==2.31.0" > requirements.txt
fi

# 安静模式安装依赖
pip install -r requirements.txt
echo -e "  ${GREEN}✔ Python 依赖就绪${NC}"

# 4. 初始化 Alist
echo -e "\n${BLUE}[4/6] 检查 Alist 配置...${NC}"
if [ ! -d "$HOME/.config/alist" ]; then
    echo -e "${YELLOW}首次运行 Alist 以生成配置文件...${NC}"
    timeout 5s alist server > /dev/null 2>&1
    echo -e "  ${GREEN}✔ Alist 初始化完成${NC}"
else
    echo -e "  ${GREEN}✔ Alist 配置文件已存在${NC}"
fi

# 5. PM2 安装检查
echo -e "\n${BLUE}[5/6] 配置后台进程管理 (PM2)...${NC}"
if ! command -v pm2 &> /dev/null; then
    echo -e "${YELLOW}正在安装 PM2...${NC}"
    npm install -g pm2
    echo -e "  ${GREEN}✔ PM2 安装完成${NC}"
else
    echo -e "  ${GREEN}✔ PM2 已安装${NC}"
fi

# 6. 启动进程 (Bot + Updater)
echo -e "\n${BLUE}[6/6] 启动服务...${NC}"
chmod +x bot.py auto_update.py

BOT_APP="termux-bot"
UPDATER_APP="termux-updater"

# --- 启动/重启 机器人 ---
if pm2 describe "$BOT_APP" > /dev/null 2>&1; then
    echo -e "🔄 重载机器人进程..."
    pm2 restart "$BOT_APP"
else
    echo -e "🚀 启动机器人进程..."
    pm2 start bot.py --name "$BOT_APP" --interpreter python
fi

# --- 启动 自动更新 (不重启，防止 setup.sh 执行中断) ---
if pm2 describe "$UPDATER_APP" > /dev/null 2>&1; then
    echo -e "🛡️  自动更新守护进程正在运行 (跳过重启)"
else
    echo -e "🛡️  启动自动更新守护进程..."
    # 启动 auto_update.py
    pm2 start auto_update.py --name "$UPDATER_APP" --interpreter python
fi

# 保存 PM2 列表
pm2 save --force > /dev/null

echo -e "\n${BLUE}=======================================${NC}"
echo -e "       ${GREEN}🚀 所有服务已就绪！${NC}"
echo -e "${BLUE}=======================================${NC}"
echo -e "进程列表："
pm2 list
echo -e "${BLUE}=======================================${NC}"
echo -e "常用命令："
echo -e "  👀 机器人日志: ${YELLOW}pm2 log $BOT_APP${NC}"
echo -e "  ♻️ 更新日志:   ${YELLOW}pm2 log $UPDATER_APP${NC}"
echo -e "  🛑 停止所有:   ${YELLOW}pm2 stop all${NC}"
