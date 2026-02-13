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

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}   Termux Bot: 全自动环境部署系统      ${NC}"
echo -e "${BLUE}=======================================${NC}"

# --- 0. 基础环境与依赖全检 ---
echo -e "\n${BLUE}[1/6] 检查系统依赖...${NC}"

# 0.1 更新源 (可选，建议首次运行手动执行 pkg update)
# pkg update -y

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
    
    # 尝试使用 pkg 安装 (部分源可能包含)
    pkg install cloudflared -y 2>/dev/null
    
    # 二次检查，如果 pkg 安装失败，则手动下载二进制
    if ! command -v cloudflared &> /dev/null; then
        echo -e "  ⚠️ 源中未找到 cloudflared，尝试下载官方二进制 (ARM64)..."
        ARCH=$(uname -m)
        if [[ "$ARCH" == "aarch64" ]]; then
            echo "  ⬇️ 下载中..."
            wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -O $PREFIX/bin/cloudflared
            chmod +x $PREFIX/bin/cloudflared
            echo -e "  ✅ Cloudflared 二进制安装完成"
        else
            echo -e "  ❌ 自动下载仅支持 aarch64 架构，当前架构: $ARCH，请手动安装。"
        fi
    fi
else
    echo -e "  ✅ 已安装: cloudflared"
fi

# 0.5 专项检查: Alist (网盘管理)
if ! command -v alist &> /dev/null; then
    echo -e "  🔍 未检测到 Alist，尝试安装..."
    
    # 尝试使用 pkg 安装
    pkg install alist -y 2>/dev/null
    
    # 二次检查
    if ! command -v alist &> /dev/null; then
        echo -e "  ⚠️ 源中未找到 Alist，尝试下载官方二进制 (ARM64)..."
        ARCH=$(uname -m)
        if [[ "$ARCH" == "aarch64" ]]; then
            echo "  ⬇️ 下载中..."
            wget -q https://github.com/alist-org/alist/releases/latest/download/alist-linux-arm64.tar.gz
            tar -zxvf alist-linux-arm64.tar.gz >/dev/null 2>&1
            mv alist $PREFIX/bin/
            rm alist-linux-arm64.tar.gz
            chmod +x $PREFIX/bin/alist
            echo -e "  ✅ Alist 二进制安装完成"
        else
            echo -e "  ❌ 自动下载仅支持 aarch64 架构，请手动安装 Alist。"
        fi
    fi
else
    echo -e "  ✅ 已安装: alist"
fi

# 0.6 专项检查: PM2 (进程管理)
if ! command -v pm2 &> /dev/null; then
    echo -e "  📦 正在安装: ${YELLOW}pm2${NC} ..."
    npm install -g pm2
else
    echo -e "  ✅ 已安装: pm2"
fi

# --- 1. Python 依赖检查 ---
echo -e "\n${BLUE}[2/6] 检查 Python 库...${NC}"
# pip 会自动跳过已安装的包，所以直接运行很安全且快速
pip install -r requirements.txt

# --- 2. 智能更新与回滚逻辑 ---
echo -e "\n${BLUE}[3/6] 检查代码更新...${NC}"
# 确保 git 安全目录
git config --global --add safe.directory "*"

UPDATED=false

if [ -d ".git" ]; then
    # 获取当前 Commit Hash (用于回滚)
    CURRENT_HASH=$(git rev-parse HEAD)
    
    # 备份配置文件 (防止 reset --hard 误删或覆盖)
    if [ -f "$CONFIG_FILE" ]; then
        cp "$CONFIG_FILE" "$BACKUP_CONFIG"
    fi

    # 拉取远程信息
    git fetch --all
    
    # 检查是否有更新
    LOCAL_HASH=$(git rev-parse HEAD)
    REMOTE_HASH=$(git rev-parse origin/main)

    if [ "$LOCAL_HASH" != "$REMOTE_HASH" ] || [ "$1" == "--force" ]; then
        echo -e "  🚀 ${YELLOW}发现新版本 (或强制更新)，正在覆盖安装...${NC}"
        
        # 强制重置到远程分支
        git reset --hard origin/main
        
        # 恢复配置文件
        if [ -f "$BACKUP_CONFIG" ]; then
            mv "$BACKUP_CONFIG" "$CONFIG_FILE"
            echo "  📂 配置文件已恢复"
        fi
        
        UPDATED=true
    else
        echo -e "  ✅ 代码已是最新"
    fi
else
    echo -e "  ⚠️ 非 Git 仓库，跳过更新检查"
fi


# --- 3. 进程管理 ---
echo -e "\n${BLUE}[4/6] 启动服务...${NC}"

# 获取 Cloudflared Token (用于固定隧道)
CF_TOKEN=""
if [ -f ".env" ]; then
    # 简单的 grep 提取，避免 source 可能带来的语法错误
    CF_TOKEN=$(grep "^CLOUDFLARED_TOKEN=" .env | cut -d'=' -f2-)
fi

# 重启函数
restart_services() {
    # 1. 启动/重启 Bot
    pm2 restart "$BOT_APP" --update-env 2>/dev/null || pm2 start bot.py --name "$BOT_APP" --interpreter python --time --output logs/bot_out.log --error logs/bot_err.log
    
    # 2. 启动/重启 Updater
    pm2 restart "$UPDATER_APP" --update-env 2>/dev/null || pm2 start auto_update.py --name "$UPDATER_APP" --interpreter python --time --output logs/updater_out.log --error logs/updater_err.log

    # 3. 启动/重启 Alist (始终启动)
    if command -v alist &> /dev/null; then
        echo -e "  🗂 正在启动 Alist (PM2)..."
        # alist server 是前台命令，适合 pm2 管理
        pm2 restart "$ALIST_APP" 2>/dev/null || pm2 start alist --name "$ALIST_APP" --interpreter none -- time -- server
    else
        echo -e "  ❌ Alist 未安装，跳过启动"
    fi

    # 4. 启动/重启 固定隧道 (如果存在 Token)
    if [ -n "$CF_TOKEN" ] && [ "${#CF_TOKEN}" -gt 20 ]; then
        echo -e "  🚇 正在启动固定隧道 (Termux-Tunnel)..."
        # 使用 --interpreter none 告诉 PM2 这是一个二进制文件
        # 使用 tunnel run 确保是固定隧道模式
        pm2 restart "$TUNNEL_APP" 2>/dev/null || pm2 start cloudflared --name "$TUNNEL_APP" --interpreter none -- time -- tunnel run --token "$CF_TOKEN"
    else
        echo -e "  ⚪ 未配置 Cloudflared Token，跳过隧道启动"
    fi
}

restart_services

# --- 4. 健康检查与回滚 ---
if [ "$UPDATED" = true ]; then
    echo -e "\n${BLUE}[5/6] 🏥 执行健康检查 (15秒)...${NC}"
    echo "  ⏳ 正在监控 Bot 启动状态..."
    
    sleep 15
    
    # 检查 PM2 状态
    IS_ONLINE=$(pm2 show "$BOT_APP" | grep "status" | grep "online")
    
    if [ -z "$IS_ONLINE" ]; then
        echo -e "\n${RED}🚨 严重警告: 新版本启动失败！${NC}"
        echo -e "${YELLOW}🔄 正在执行自动回滚 (Rollback) 到版本: ${CURRENT_HASH:0:7}...${NC}"
        
        git reset --hard "$CURRENT_HASH"
        restart_services
        
        echo -e "${GREEN}✅ 回滚完成。Bot 已恢复到旧版本。${NC}"
    else
        echo -e "${GREEN}✅ 健康检查通过！系统更新成功。${NC}"
    fi
fi

# --- 5. 保存 PM2 状态 (Termux 重启后恢复) ---
echo -e "\n${BLUE}[6/6] 保存进程状态...${NC}"
pm2 save

echo -e "\n${BLUE}=======================================${NC}"
echo -e "       ${GREEN}🚀 系统运行中${NC}"
echo -e "       输入 ${YELLOW}pm2 list${NC} 查看状态"
echo -e "${BLUE}=======================================${NC}"
