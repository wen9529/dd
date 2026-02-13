#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 获取脚本所在绝对路径，确保 PM2 在正确目录下运行
CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$CURRENT_DIR"

BOT_APP="termux-bot"
UPDATER_APP="termux-updater"
TUNNEL_APP="termux-tunnel"
ALIST_APP="termux-alist"
CONFIG_FILE="bot_config.json"
BACKUP_CONFIG="$CURRENT_DIR/bot_config.bak"

# 创建日志目录
mkdir -p "$CURRENT_DIR/logs"

# 修复启动脚本权限
if [ -f "start.sh" ]; then
    chmod +x start.sh
fi

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}   Termux Bot: 全自动环境部署系统      ${NC}"
echo -e "${BLUE}=======================================${NC}"
echo -e "📂 工作目录: $CURRENT_DIR"

# --- 0. 基础环境与依赖全检 ---
echo -e "\n${BLUE}[1/6] 检查系统依赖...${NC}"

check_and_install() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "  📦 正在安装: ${YELLOW}$1${NC} ..."
        pkg install "$1" -y
    else
        echo -e "  ✅ 已安装: $1"
    fi
}

DEPENDENCIES=("python" "ffmpeg" "aria2" "git" "nodejs" "wget" "openssl-tool" "proot" "tar")
for dep in "${DEPENDENCIES[@]}"; do
    check_and_install "$dep"
done

# Cloudflared 检查
if ! command -v cloudflared &> /dev/null; then
    echo -e "  🔍 未检测到 cloudflared，尝试安装..."
    pkg install cloudflared -y 2>/dev/null
    if ! command -v cloudflared &> /dev/null; then
        echo -e "  ⚠️ 源中未找到 cloudflared，尝试下载官方二进制 (ARM64)..."
        ARCH=$(uname -m)
        if [[ "$ARCH" == "aarch64" ]]; then
            wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -O $PREFIX/bin/cloudflared
            chmod +x $PREFIX/bin/cloudflared
        fi
    fi
fi

# Alist 检查
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
        fi
    fi
fi

# PM2 检查
if ! command -v pm2 &> /dev/null; then
    echo -e "  📦 正在安装: ${YELLOW}pm2${NC} ..."
    npm install -g pm2
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
fi


# --- 3. 进程管理 ---
echo -e "\n${BLUE}[4/6] 启动服务...${NC}"

# 寻找 .env
ENV_FILE=""
if [ -f ".env" ]; then ENV_FILE=".env"; elif [ -f "$HOME/.env" ]; then ENV_FILE="$HOME/.env"; fi

# 获取 Cloudflared Token
CF_TOKEN=""
if [ -n "$ENV_FILE" ]; then
    echo -e "  🔍 加载配置文件: $ENV_FILE"
    CF_TOKEN=$(grep "^CLOUDFLARED_TOKEN" "$ENV_FILE" 2>/dev/null | awk -F '=' '{print $2}' | tr -d '"' | tr -d "'")
fi

restart_services() {
    # 强制重新加载 PM2 配置
    # 使用 delete + start 确保 cwd 参数生效
    
    PYTHON_EXEC=$(command -v python)
    
    echo -e "  🔄 正在重置 PM2 进程 (使用绝对路径)..."

    # 1. Bot (保留日志)
    pm2 delete "$BOT_APP" &>/dev/null
    pm2 start "$CURRENT_DIR/bot.py" --name "$BOT_APP" --interpreter "$PYTHON_EXEC" --cwd "$CURRENT_DIR" --time --output "$CURRENT_DIR/logs/bot_out.log" --error "$CURRENT_DIR/logs/bot_err.log" --restart-delay 3000

    # 2. Updater (保留日志)
    pm2 delete "$UPDATER_APP" &>/dev/null
    pm2 start "$CURRENT_DIR/auto_update.py" --name "$UPDATER_APP" --interpreter "$PYTHON_EXEC" --cwd "$CURRENT_DIR" --time --output "$CURRENT_DIR/logs/updater_out.log" --error "$CURRENT_DIR/logs/updater_err.log" --restart-delay 60000

    # 3. Alist (新增日志)
    if command -v alist &> /dev/null; then
        echo -e "  🗂 启动 Alist..."
        ALIST_EXEC=$(command -v alist)
        pm2 delete "$ALIST_APP" &>/dev/null
        pm2 start "$ALIST_EXEC" --name "$ALIST_APP" --interpreter none --cwd "$CURRENT_DIR" --output "$CURRENT_DIR/logs/alist_out.log" --error "$CURRENT_DIR/logs/alist_err.log" -- server
    fi

    # 4. Tunnel (新增日志)
    if [ -n "$CF_TOKEN" ] && [ "${#CF_TOKEN}" -gt 20 ]; then
        if command -v cloudflared &> /dev/null; then
            echo -e "  🚇 启动 Cloudflared 隧道..."
            CF_EXEC=$(command -v cloudflared)
            pm2 delete "$TUNNEL_APP" &>/dev/null
            # 这里不使用 --logfile 参数，而是让 pm2 捕获 stdout/stderr，因为 cloudflared 默认输出到 stderr
            pm2 start "$CF_EXEC" --name "$TUNNEL_APP" --interpreter none --cwd "$CURRENT_DIR" --output "$CURRENT_DIR/logs/tunnel_out.log" --error "$CURRENT_DIR/logs/tunnel_err.log" -- tunnel run --token "$CF_TOKEN"
        fi
    else
        echo -e "  ⚪ 跳过隧道启动: Token 未配置或无效"
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

# 检查 Token
TOKEN_STATUS="❓ 未知"
if [ -n "$ENV_FILE" ]; then
    if grep -q "TG_BOT_TOKEN=." "$ENV_FILE" 2>/dev/null; then
        TOKEN_STATUS="✅ 已配置"
    else
        TOKEN_STATUS="❌ 未配置 (Bot将进入休眠模式)"
    fi
else
    TOKEN_STATUS="❌ .env 文件缺失"
fi

echo -e "\n${BLUE}=======================================${NC}"
echo -e "       ${GREEN}🚀 系统运行中${NC}"
echo -e "       Bot Token: ${TOKEN_STATUS}"
echo -e "       Alist 状态: $(pm2 show $ALIST_APP | grep status | awk '{print $4}')"
echo -e "${BLUE}=======================================${NC}"
