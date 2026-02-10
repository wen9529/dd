#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

clear
echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}   Termux Bot: 强制更新与部署工具      ${NC}"
echo -e "${BLUE}=======================================${NC}"

# 0. 权限与Git安全修复
echo -e "${BLUE}[0/7] 正在修复权限与 Git 配置...${NC}"
git config --global --add safe.directory "*"
chmod -R 755 .
chmod +x *.py *.sh

# 1. 智能强制更新 (关键步骤)
if [ -d ".git" ]; then
    echo -e "\n${BLUE}[1/7] 正在强制拉取最新代码...${NC}"
    
    # 暂存本地修改（保存您填写的 Token 和 ID）
    echo "  💾 正在暂存您的配置文件..."
    git stash > /dev/null 2>&1
    
    # 拉取最新代码
    echo "  ⬇️  从服务器拉取更新..."
    git pull
    
    # 恢复本地修改
    echo "  📂 恢复您的配置文件..."
    git stash pop > /dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        echo -e "  ${GREEN}✔ 更新成功且配置已保留${NC}"
    else
        echo -e "  ${YELLOW}⚠️  恢复配置时可能遇到冲突，请检查 bot.py 内容是否正确${NC}"
    fi
else
    echo -e "\n${BLUE}[1/7] 非 Git 仓库，跳过更新${NC}"
fi

# 2. 系统依赖检测
echo -e "\n${BLUE}[2/7] 检查并安装系统组件...${NC}"
# 函数：检查并安装软件包
check_install() {
    pkg_name=$1
    bin_name=$2
    if [ -z "$bin_name" ]; then bin_name=$pkg_name; fi
    if ! command -v "$bin_name" &> /dev/null; then
        echo -e "  正在安装 $pkg_name ..."
        pkg install "$pkg_name" -y > /dev/null 2>&1
    else
        echo -e "  ${GREEN}✔ $pkg_name 已安装${NC}"
    fi
}

check_install "git"
check_install "python"
check_install "nodejs" "node"
check_install "ffmpeg"
check_install "alist"

# 3. Python 依赖
echo -e "\n${BLUE}[3/7] 检查 Python 库...${NC}"
if [ ! -f "requirements.txt" ]; then
    echo -e "python-telegram-bot==20.8\npsutil==5.9.8\nrequests==2.31.0" > requirements.txt
fi
pip install -r requirements.txt > /dev/null 2>&1
echo -e "  ${GREEN}✔ Python 依赖就绪${NC}"

# 4. 初始化 Alist
echo -e "\n${BLUE}[4/7] 检查 Alist...${NC}"
if [ ! -d "$HOME/.config/alist" ]; then
    timeout 5s alist server > /dev/null 2>&1
fi
echo -e "  ${GREEN}✔ Alist 就绪${NC}"

# 5. 环境自检
echo -e "\n${BLUE}[5/7] 🔎 最终环境验证...${NC}"
if command -v ffmpeg &> /dev/null; then
    echo -e "  🎥 FFmpeg: ${GREEN}OK${NC}"
else
    echo -e "  🎥 FFmpeg: ${RED}未找到 (请手动 pkg install ffmpeg)${NC}"
fi

# 6. PM2 安装检查
echo -e "\n${BLUE}[6/7] 配置 PM2...${NC}"
if ! command -v pm2 &> /dev/null; then
    npm install -g pm2 > /dev/null 2>&1
fi

# 7. 启动进程 (强制重启以应用新代码)
echo -e "\n${BLUE}[7/7] 重启服务...${NC}"
BOT_APP="termux-bot"
UPDATER_APP="termux-updater"

pm2 delete "$BOT_APP" > /dev/null 2>&1
pm2 delete "$UPDATER_APP" > /dev/null 2>&1

pm2 start bot.py --name "$BOT_APP" --interpreter python --time
pm2 start auto_update.py --name "$UPDATER_APP" --interpreter python --time
pm2 save --force > /dev/null

echo -e "\n${BLUE}=======================================${NC}"
echo -e "       ${GREEN}🚀 机器人已重启并更新！${NC}"
echo -e "${BLUE}=======================================${NC}"
echo -e "现在请去 Telegram 向机器人发送 ${YELLOW}/start${NC}"
echo -e "如果看不到菜单，机器人会回复您的 ID，请核对 bot.py 中的配置。"
