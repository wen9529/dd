#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

BOT_APP="termux-bot"
UPDATER_APP="termux-updater"
TUNNEL_APP="termux-tunnel"
ALIST_APP="termux-alist"
CONFIG_FILE="bot_config.json"
BACKUP_CONFIG="/data/data/com.termux/files/usr/tmp/bot_config.bak"

# 修复启动脚本权限
if [ -f "start.sh" ]; then
    chmod +x start.sh
fi

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}   Termux Bot: 全自动环境部署系统      ${NC}"
echo -e "${BLUE}=======================================${NC}"

# --- 0. 基础环境与依赖全检 ---
echo -e "\n${BLUE}[1/6] 检查系统依赖...${NC}"

# 0.2 定义检查安装函数
check_and_install() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "  📦 正在安装: ${YELLOW}$1${NC} ..."
        pkg install "$1" -y
    else
        echo -e "  ✅ 已安装: $1"
    fi
}

# 0.3 批量检查基础软件包
DEPENDENCIES=("python" "ffmpeg" "aria2" "git" "nodejs" "wget" "openssl-tool" "proot" "tar")
for dep in "${DEPENDENCIES[@]}"; do
    check_and_install "$dep"
done

# 0.4 专项检查: Cloudflared (内网穿透)
if ! command -v cloudflared &> /dev/null; then
    echo -e "  🔍 未检测到 cloudflared，尝试安装..."
    pkg install cloudflared -y 2>/dev/null
    if ! command -v cloudflared &> /dev/null; then
        echo -e "  ⚠️ 源中未找到 cloudflared，尝试下载官方二进制 (ARM64)..."
        ARCH=$(uname -m)
        if [[ "$ARCH" == "aarch64" ]]; then
            wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -O $PREFIX/bin/cloudflared
            chmod +x $PREFIX/bin/cloudflared
            echo -e "  ✅ Cloudflared 二进制安装完成"
        else
            echo -e "  ❌ 自动下载仅支持 aarch64 架构，请手动安装。"
        fi
    fi
else
    echo -e "  ✅ 已安装: cloudflared"
fi

# 0.5 专项检查: Alist (网盘管理)
if ! command -v alist &> /dev/null; then
    echo -e "  🔍 未检测到 Alist，尝试安装..."
    pkg install alist -y 2>/dev/null
    if ! command -v alist &> /dev/null; then
        echo -e "  ⚠️ 源中未找到 Alist，尝试下载官方二进制 (ARM64)..."
        ARCH=$(uname -m)
        if [[ "$ARCH" == "aarch64" ]]; then
            wget -q https://github.com/alist-org/alist/releases/latest/download/alist-linux-arm64.tar.gz
            tar -zxvf alist-linux-arm64.tar.gz >/dev/null 2>&1
            mv alist $PREFIX/bin/
            rm alist-linux-arm64.tar.gz
            chmod +x $PREFIX/bin/alist
            echo -e "  ✅ Alist 二进制安装完成"
        else
            echo -e "  ❌ 自动下载仅支持 aarch64 架构，请手动安装。"
        fi
    fi
else
    echo -e "  ✅ 已安装: alist"
fi

# 0.6 专项检查: PM2
if ! command -v pm2 &> /dev/null; then
    echo -e "  📦 正在安装: ${YELLOW}pm2${NC} ..."
    npm install -g pm2
else
    echo -e "  ✅ 已安装: pm2"
fi

# --- 1. Python 依赖检查 ---
echo -e "\n${BLUE}[2/6] 检查 Python 库...${NC}"
pip install -r requirements.txt

# --- 2. 智能更新与回滚逻辑 ---
echo -e "\n${BLUE}[3/6] 检查代码更新...${NC}"
git config --global --add safe.directory "*"
UPDATED=false
if [ -d ".git" ]; then
    CURRENT_HASH=$(git rev-parse HEAD)
    if [ -f "$CONFIG_FILE" ]; then cp "$CONFIG_FILE" "$BACKUP_CONFIG"; fi
    git fetch --all
    LOCAL_HASH=$(git rev-parse HEAD)
    REMOTE_HASH=$(git rev-parse origin/main)

    if [ "$LOCAL_HASH" != "$REMOTE_HASH" ] || [ "$1" == "--force" ]; then
        echo -e "  🚀 ${YELLOW}发现新版本，正在更新...${NC}"
        git reset --hard origin/main
        if [ -f "$BACKUP_CONFIG" ]; then mv "$BACKUP_CONFIG" "$CONFIG_FILE"; fi
        UPDATED=true
    else
        echo -e "  ✅ 代码已是最新"
    fi
else
    echo -e "  ⚠️ 非 Git 仓库，跳过更新检查"
fi


# --- 3. 进程管理 ---
echo -e "\n${BLUE}[4/6] 启动服务...${NC}"

# 强力获取 Cloudflared Token
CF_TOKEN=""
if [ -f ".env" ]; then
    # 使用 awk/sed 处理可能的引号和空格，更稳健
    CF_TOKEN=$(grep "^CLOUDFLARED_TOKEN" .env 2>/dev/null | awk -F '=' '{print $2}' | tr -d '"' | tr -d "'")
fi

# 重启函数
restart_services() {
    # 1. Bot (解释器 python)
    pm2 restart "$BOT_APP" --update-env 2>/dev/null || pm2 start bot.py --name "$BOT_APP" --interpreter python --time --output logs/bot_out.log --error logs/bot_err.log
    
    # 2. Updater (解释器 python)
    pm2 restart "$UPDATER_APP" --update-env 2>/dev/null || pm2 start auto_update.py --name "$UPDATER_APP" --interpreter python --time --output logs/updater_out.log --error logs/updater_err.log

    # 3. Alist (解释器 none, 二进制)
    # 移除 'time' 参数，修复启动错误
    if command -v alist &> /dev/null; then
        echo -e "  🗂 启动 Alist..."
        pm2 restart "$ALIST_APP" 2>/dev/null || pm2 start alist --name "$ALIST_APP" --interpreter none -- server
    fi

    # 4. Tunnel (解释器 none, 二进制)
    # 移除 'time' 参数，修复启动错误
    if [ -n "$CF_TOKEN" ] && [ "${#CF_TOKEN}" -gt 20 ]; then
        echo -e "  🚇 启动固定隧道 (Cloudflared)..."
        echo -e "     Token 前缀: ${CF_TOKEN:0:10}..."
        pm2 restart "$TUNNEL_APP" 2>/dev/null || pm2 start cloudflared --name "$TUNNEL_APP" --interpreter none -- tunnel run --token "$CF_TOKEN"
    else
        echo -e "  ⚪ 跳过隧道启动: 未在 .env 找到有效 CLOUDFLARED_TOKEN"
    fi
}

restart_services

# --- 4. 健康检查 ---
if [ "$UPDATED" = true ]; then
    echo -e "\n${BLUE}[5/6] 🏥 执行健康检查 (10秒)...${NC}"
    sleep 10
    IS_ONLINE=$(pm2 show "$BOT_APP" | grep "status" | grep "online")
    if [ -z "$IS_ONLINE" ]; then
        echo -e "\n${RED}🚨 警告: 启动失败，正在回滚...${NC}"
        git reset --hard "$CURRENT_HASH"
        restart_services
        echo -e "${GREEN}✅ 已回滚到旧版本${NC}"
    else
        echo -e "${GREEN}✅ 更新成功${NC}"
    fi
fi

# --- 5. 保存状态 ---
echo -e "\n${BLUE}[6/6] 保存进程状态...${NC}"
pm2 save

# 检查 Token 状态
TOKEN_STATUS="❓ 未知"
if [ -f ".env" ]; then
    if grep -q "TG_BOT_TOKEN=." .env 2>/dev/null; then
        TOKEN_STATUS="✅ 已配置"
    else
        TOKEN_STATUS="❌ 未配置 (Bot将进入休眠，请编辑 .env)"
    fi
else
    TOKEN_STATUS="❌ .env 文件缺失"
fi

echo -e "\n${BLUE}=======================================${NC}"
echo -e "       ${GREEN}🚀 系统运行中${NC}"
echo -e "       Bot Token 状态: ${TOKEN_STATUS}"
echo -e "       输入 ${YELLOW}pm2 list${NC} 查看详细状态"
echo -e "${BLUE}=======================================${NC}"
