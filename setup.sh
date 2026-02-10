#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 确保在脚本出错时不会立即退出，尝试执行完后续逻辑
set +e

clear
echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}   Termux Bot: 强制更新与部署工具      ${NC}"
echo -e "${BLUE}=======================================${NC}"

# 配置 git 用户信息，防止 stash 失败
git config --global user.email "bot@termux.local"
git config --global user.name "TermuxBot"
git config --global --add safe.directory "*"

# 1. 智能强制更新
if [ -d ".git" ]; then
    echo -e "\n${BLUE}[1/6] 正在检查更新...${NC}"
    
    # 暂存本地修改（保存您填写的 Token 和 ID）
    echo "  💾 正在暂存您的本地修改..."
    git stash
    
    # 拉取最新代码
    echo "  ⬇️  从服务器拉取更新..."
    git pull origin main
    
    # 恢复本地修改
    echo "  📂 恢复您的本地修改..."
    git stash pop
    
    if [ $? -eq 0 ]; then
        echo -e "  ${GREEN}✔ 代码更新完成${NC}"
    else
        echo -e "  ${YELLOW}⚠️  恢复配置时遇到冲突，将优先使用 git 上的新版本。请检查 bot_config.json 是否保留了您的配置。${NC}"
    fi
else
    echo -e "\n${BLUE}[1/6] 非 Git 仓库，跳过更新${NC}"
fi

# 2. 权限修复
echo -e "\n${BLUE}[2/6] 修复权限...${NC}"
chmod +x *.py *.sh
chmod 755 .

# 3. 依赖安装
echo -e "\n${BLUE}[3/6] 检查依赖...${NC}"
if ! command -v ffmpeg &> /dev/null; then
    pkg install ffmpeg -y
fi
if ! command -v alist &> /dev/null; then
    pkg install alist -y
fi
pip install -r requirements.txt > /dev/null 2>&1

# 4. PM2 守护进程配置
echo -e "\n${BLUE}[4/6] 配置后台进程...${NC}"
if ! command -v pm2 &> /dev/null; then
    npm install -g pm2
fi

BOT_APP="termux-bot"
UPDATER_APP="termux-updater"

# 5. 重启逻辑 (优化：使用 restart 而不是 delete，防止进程丢失)
echo -e "\n${BLUE}[5/6] 重启服务...${NC}"

# 检查 termux-bot 是否存在
pm2 describe "$BOT_APP" > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "  🔄 重启机器人进程..."
    pm2 restart "$BOT_APP" --update-env
else
    echo "  🚀 启动机器人进程..."
    pm2 start bot.py --name "$BOT_APP" --interpreter python --time
fi

# 检查 updater 是否存在
pm2 describe "$UPDATER_APP" > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "  🔄 重启更新守护进程..."
    pm2 restart "$UPDATER_APP" --update-env
else
    echo "  🚀 启动更新守护进程..."
    pm2 start auto_update.py --name "$UPDATER_APP" --interpreter python --time
fi

# 保存当前进程列表
pm2 save --force > /dev/null 2>&1

echo -e "\n${BLUE}=======================================${NC}"
echo -e "       ${GREEN}🚀 部署完成！${NC}"
echo -e "${BLUE}=======================================${NC}"
echo -e "机器人正在后台运行。"
echo -e "日志查看: ${YELLOW}pm2 log termux-bot${NC}"
