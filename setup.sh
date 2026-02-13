#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

BOT_APP="termux-bot"
UPDATER_APP="termux-updater"
CONFIG_FILE="bot_config.json"
BACKUP_CONFIG="/data/data/com.termux/files/usr/tmp/bot_config.bak"

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}   Termux Bot: 智能部署与容灾系统      ${NC}"
echo -e "${BLUE}=======================================${NC}"

# --- 0. 环境预检 ---
mkdir -p downloads logs data
# 确保 git 安全目录
git config --global --add safe.directory "*"

# --- 1. 智能更新与回滚逻辑 ---
if [ -d ".git" ]; then
    echo -e "\n${BLUE}[1/6] 检查代码更新...${NC}"
    
    # 获取当前 Commit Hash (用于回滚)
    CURRENT_HASH=$(git rev-parse HEAD)
    
    # 备份配置文件 (防止 reset --hard 误删或覆盖)
    if [ -f "$CONFIG_FILE" ]; then
        cp "$CONFIG_FILE" "$BACKUP_CONFIG"
        echo "  💾 配置文件已备份"
    fi

    # 拉取远程信息
    git fetch --all
    
    # 检查是否有更新
    LOCAL_HASH=$(git rev-parse HEAD)
    REMOTE_HASH=$(git rev-parse origin/main)

    if [ "$LOCAL_HASH" != "$REMOTE_HASH" ] || [ "$1" == "--force" ]; then
        echo -e "  🚀 ${YELLOW}发现新版本 (或强制更新)，正在覆盖安装...${NC}"
        
        # 强制重置到远程分支 (丢弃本地修改，确保代码一致性)
        git reset --hard origin/main
        
        # 恢复配置文件
        if [ -f "$BACKUP_CONFIG" ]; then
            # 如果新版本没有该文件，或者需要保留旧配置
            # 这里简单策略：如果有备份，且当前文件不存在或被重置，尝试合并或恢复
            # 由于 bot_config.json 通常由 bot 生成，我们优先使用备份的
            mv "$BACKUP_CONFIG" "$CONFIG_FILE"
            echo "  📂 配置文件已恢复"
        fi
        
        UPDATED=true
    else
        echo -e "  ✅ 当前已是最新版本"
        UPDATED=false
    fi
else
    echo -e "  ⚠️ 非 Git 仓库，跳过更新检查"
fi

# --- 2. 依赖安装 ---
echo -e "\n${BLUE}[2/6] 依赖检查...${NC}"
chmod +x *.py *.sh
# 仅在更新后或强制模式下运行繁重的依赖安装
if [ "$UPDATED" = true ] || [ "$1" == "--force" ]; then
    pip install -r requirements.txt > /dev/null 2>&1
    echo "  📦 Python 依赖已更新"
fi

# --- 3. 进程管理与健康检查 ---
echo -e "\n${BLUE}[3/6] 重启服务...${NC}"

# 安装 PM2 (如果缺失)
if ! command -v pm2 &> /dev/null; then
    npm install -g pm2
fi

# 重启函数
restart_services() {
    pm2 restart "$BOT_APP" --update-env 2>/dev/null || pm2 start bot.py --name "$BOT_APP" --interpreter python --time --output logs/bot_out.log --error logs/bot_err.log
    pm2 restart "$UPDATER_APP" --update-env 2>/dev/null || pm2 start auto_update.py --name "$UPDATER_APP" --interpreter python --time --output logs/updater_out.log --error logs/updater_err.log
}

restart_services

# --- 4. 关键：健康检查与回滚 ---
if [ "$UPDATED" = true ]; then
    echo -e "\n${BLUE}[4/6] 🏥 执行健康检查 (15秒)...${NC}"
    echo "  ⏳ 正在监控 Bot 启动状态..."
    
    # 等待进程初始化
    sleep 15
    
    # 检查 PM2 状态
    # 如果 status 不是 online，或者 restart_time > 1 (说明这15秒内反复重启了)
    IS_ONLINE=$(pm2 show "$BOT_APP" | grep "status" | grep "online")
    
    if [ -z "$IS_ONLINE" ]; then
        echo -e "\n${RED}🚨 严重警告: 新版本启动失败！${NC}"
        echo -e "${YELLOW}🔄 正在执行自动回滚 (Rollback) 到版本: ${CURRENT_HASH:0:7}...${NC}"
        
        # 回滚代码
        git reset --hard "$CURRENT_HASH"
        
        # 再次重启
        restart_services
        
        echo -e "${GREEN}✅ 回滚完成。Bot 已恢复到旧版本。${NC}"
        echo -e "请检查日志: pm2 log $BOT_APP"
        
        # 可以选择在这里发送通知 (如果有一个独立的 notify 脚本)
    else
        echo -e "${GREEN}✅ 健康检查通过！系统更新成功。${NC}"
    fi
fi

echo -e "\n${BLUE}=======================================${NC}"
echo -e "       ${GREEN}🚀 部署流程结束${NC}"
echo -e "${BLUE}=======================================${NC}"
