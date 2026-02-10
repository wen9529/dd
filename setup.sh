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

    echo -n "检查 $pkg_name ... "
    if ! command -v "$bin_name" &> /dev/null; then
        echo -e "${YELLOW}未安装，开始安装...${NC}"
        pkg install "$pkg_name" -y
        if [ $? -ne 0 ]; then
             echo -e "${RED}安装 $pkg_name 失败，请尝试手动运行 'pkg install $pkg_name'${NC}"
        fi
    else
        echo -e "${GREEN}✔ 已安装${NC}"
    fi
}

# 1. 手动/首次运行时的更新检查
if [ -d ".git" ]; then
    echo -e "\n${BLUE}[1/7] 检查代码更新 (手动触发)...${NC}"
    if git pull --rebase 2>&1 | grep -q "Already up to date"; then
        echo "  当前已是最新版本。"
    else
        echo -e "  ${GREEN}✔ 代码已更新${NC}"
    fi
else
    echo -e "\n${BLUE}[1/7] 非 Git 仓库，跳过更新检查${NC}"
fi

# 2. 系统依赖检测
echo -e "\n${BLUE}[2/7] 检查并安装系统组件...${NC}"
check_install "git"
check_install "python"
check_install "nodejs" "node"
check_install "ffmpeg"        # 核心：用于推流
check_install "alist"         # 核心：用于网盘

# 3. Python 依赖
echo -e "\n${BLUE}[3/7] 检查 Python 库...${NC}"
if [ ! -f "requirements.txt" ]; then
    echo "创建默认 requirements.txt..."
    echo -e "python-telegram-bot==20.8\npsutil==5.9.8\nrequests==2.31.0" > requirements.txt
fi
pip install -r requirements.txt
echo -e "  ${GREEN}✔ Python 依赖就绪${NC}"

# 4. 初始化 Alist
echo -e "\n${BLUE}[4/7] 检查 Alist 配置文件...${NC}"
if [ ! -d "$HOME/.config/alist" ]; then
    echo -e "${YELLOW}首次运行 Alist 生成配置...${NC}"
    timeout 5s alist server > /dev/null 2>&1
    echo -e "  ${GREEN}✔ 初始化完成${NC}"
else
    echo -e "  ${GREEN}✔ 配置文件存在${NC}"
fi

# 5. 环境自检 (新增)
echo -e "\n${BLUE}[5/7] 🔎 最终环境验证...${NC}"
echo "---------------------------------------"

if command -v ffmpeg &> /dev/null; then
    ff_ver=$(ffmpeg -version | head -n 1 | awk '{print $3}')
    echo -e "🎥 FFmpeg: ${GREEN}已安装${NC} (版本: $ff_ver)"
else
    echo -e "🎥 FFmpeg: ${RED}未找到!${NC} 请手动运行 pkg install ffmpeg"
fi

if command -v alist &> /dev/null; then
    alist_ver=$(alist version | grep Version | awk '{print $2}')
    echo -e "🗂  Alist : ${GREEN}已安装${NC} (版本: $alist_ver)"
else
    echo -e "🗂  Alist : ${RED}未找到!${NC} 请手动运行 pkg install alist"
fi
echo "---------------------------------------"

# 6. PM2 安装检查
echo -e "\n${BLUE}[6/7] 配置 PM2 进程守护...${NC}"
if ! command -v pm2 &> /dev/null; then
    echo -e "${YELLOW}正在安装 PM2...${NC}"
    npm install -g pm2
    echo -e "  ${GREEN}✔ PM2 安装完成${NC}"
else
    echo -e "  ${GREEN}✔ PM2 已安装${NC}"
fi

# 7. 启动进程
echo -e "\n${BLUE}[7/7] 启动服务...${NC}"
chmod +x bot.py auto_update.py

BOT_APP="termux-bot"
UPDATER_APP="termux-updater"

# 启动 Bot
if pm2 describe "$BOT_APP" > /dev/null 2>&1; then
    echo -e "🔄 重载机器人进程..."
    pm2 restart "$BOT_APP"
else
    echo -e "🚀 启动机器人进程..."
    pm2 start bot.py --name "$BOT_APP" --interpreter python
fi

# 启动自动更新
if pm2 describe "$UPDATER_APP" > /dev/null 2>&1; then
    echo -e "🛡️  自动更新守护进程运行中"
else
    echo -e "🛡️  启动自动更新守护进程..."
    pm2 start auto_update.py --name "$UPDATER_APP" --interpreter python
fi

pm2 save --force > /dev/null

echo -e "\n${BLUE}=======================================${NC}"
echo -e "       ${GREEN}🚀 服务启动成功！${NC}"
echo -e "${BLUE}=======================================${NC}"
echo -e "提示: 如果上方显示 FFmpeg 或 Alist 未安装，"
echo -e "请尝试执行: pkg install ffmpeg alist -y"
echo -e "${BLUE}=======================================${NC}"
