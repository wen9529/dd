import logging
import asyncio
import subprocess
import os
import signal
import psutil
import sys
import socket
import json
from urllib.parse import quote
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# --- ⚠️ 核心配置区域 ⚠️ ---
# 您执行了 reset，配置可能已丢失。
# 请在此处填入您的 Token 和 ID，或者在 Web 界面/本地编辑器修改。
TOKEN = "7565918204:AAH3E3Bb9Op7Xv-kezL6GISeJj8mA6Ycwug" 
OWNER_ID = 1878794912
# -------------------------

CONFIG_FILE = "bot_config.json"
# 全局变量用于存储 FFmpeg 进程
ffmpeg_process = None

# 配置日志 - 输出到标准输出以便 pm2 log 查看
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

def is_owner(user_id):
    """检查用户是否为管理员，并打印调试日志"""
    uid_str = str(user_id).strip()
    owner_str = str(OWNER_ID).strip()
    
    is_match = uid_str == owner_str
    
    if is_match:
        print(f"✅ [权限通过] 用户 {uid_str} 正在操作")
    else:
        print(f"❌ [权限拒绝] 用户 {uid_str} 尝试操作，但管理员ID设定为 {owner_str}")
        
    return is_match

# --- 配置管理 ---
def load_config():
    """加载配置文件"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
    return {}

def save_config(config):
    """保存配置文件"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        logger.error(f"保存配置失败: {e}")

# --- 辅助功能 ---
def check_program(cmd):
    """检查程序版本"""
    try:
        if cmd == "ffmpeg":
            output = subprocess.check_output(["ffmpeg", "-version"], stderr=subprocess.STDOUT, text=True)
            return output.splitlines()[0].split()[2] 
        elif cmd == "alist":
            output = subprocess.check_output(["alist", "version"], stderr=subprocess.STDOUT, text=True)
            for line in output.splitlines():
                if "Version" in line:
                    return line.split(":")[-1].strip()
            return "Unknown"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

def get_alist_pid():
    """查找 alist 进程 PID"""
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if 'alist' in proc.info['name']:
                return proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None

def get_local_ip():
    """
    获取本机局域网 IP。
    优化逻辑：优先检测 Wi-Fi (wlan0) 和 有线 (eth0)，忽略 VPN (tun) 接口。
    """
    try:
        # 获取所有网络接口
        interfaces = psutil.net_if_addrs()
        
        # 1. 优先列表：Termux/Android 下通常 Wi-Fi 是 wlan0
        priority_interfaces = ['wlan0', 'eth0', 'wlan1']
        
        for iface in priority_interfaces:
            if iface in interfaces:
                for snic in interfaces[iface]:
                    if snic.family == socket.AF_INET:
                        # print(f"✅ 从优先接口 {iface} 获取到 IP: {snic.address}")
                        return snic.address

        # 2. 如果优先接口没找到，遍历其他接口，但排除 VPN 和 本地回环
        exclude_prefixes = ('tun', 'ppp', 'lo', 'docker', 'veth', 'rmnet')
        
        for name, snics in interfaces.items():
            if name.lower().startswith(exclude_prefixes):
                continue
            
            for snic in snics:
                if snic.family == socket.AF_INET and not snic.address.startswith("127."):
                    # print(f"ℹ️ 从接口 {name} 获取到 IP: {snic.address}")
                    return snic.address

        return "127.0.0.1"

    except Exception as e:
        print(f"❌ 获取 IP 出错: {e}")
        return "127.0.0.1"

def get_env_report():
    """生成环境报告文本"""
    ffmpeg_ver = check_program("ffmpeg")
    alist_ver = check_program("alist")
    alist_pid = get_alist_pid()
    ffmpeg_running = ffmpeg_process is not None and ffmpeg_process.poll() is None
    local_ip = get_local_ip()
    
    cpu_usage = psutil.cpu_percent(interval=None)
    mem_info = psutil.virtual_memory()
    mem_usage = f"{mem_info.used / 1024 / 1024:.0f}MB / {mem_info.total / 1024 / 1024:.0f}MB"

    return (
        f"🖥 **服务器环境报告**\n\n"
        f"🌐 **局域网IP**: `{local_ip}`\n(已过滤 VPN 地址)\n\n"
        f"🎥 **FFmpeg**:\n"
        f"• 安装状态: {'✅ ' + ffmpeg_ver if ffmpeg_ver else '❌ 未安装'}\n"
        f"• 推流任务: {'🔴 进行中' if ffmpeg_running else '⚪ 空闲'}\n\n"
        f"🗂 **Alist**:\n"
        f"• 安装状态: {'✅ ' + alist_ver if alist_ver else '❌ 未安装'}\n"
        f"• 运行状态: {'🟢 运行中 (PID ' + str(alist_pid) + ')' if alist_pid else '🔴 已停止'}\n\n"
        f"⚙️ **系统资源**:\n"
        f"• CPU: {cpu_usage}%\n"
        f"• 内存: {mem_usage}"
    )

# --- 键盘菜单 ---
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗂 Alist 管理", callback_data="btn_alist"), InlineKeyboardButton("📺 推流说明", callback_data="btn_stream_help")],
        [InlineKeyboardButton("🔍 环境自检", callback_data="btn_env"), InlineKeyboardButton("♻️ 检查更新", callback_data="btn_update")],
        [InlineKeyboardButton("🔄 刷新菜单", callback_data="btn_refresh")]
    ])

def get_alist_keyboard(is_running):
    start_stop_btn = InlineKeyboardButton("🔴 停止服务", callback_data="btn_alist_stop") if is_running else InlineKeyboardButton("🟢 启动服务", callback_data="btn_alist_start")
    return InlineKeyboardMarkup([
        [start_stop_btn],
        [InlineKeyboardButton("ℹ️ 访问地址", callback_data="btn_alist_info"), InlineKeyboardButton("🔑 管理密码", callback_data="btn_alist_admin")],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="btn_back_main")]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回主菜单", callback_data="btn_back_main")]])

# --- 回调处理 ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_owner(user_id):
        await query.answer("❌ 无权操作，请检查 bot.py 配置", show_alert=True)
        return

    await query.answer()
    data = query.data

    if data == "btn_refresh" or data == "btn_back_main":
        await query.edit_message_text(
            f"👑 **Termux 控制台**\n当前用户: `{user_id}`\n",
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown'
        )
    elif data == "btn_env":
        await query.edit_message_text(get_env_report(), reply_markup=get_back_keyboard(), parse_mode='Markdown')
    elif data == "btn_alist":
        pid = get_alist_pid()
        status_text = f"✅ 运行中 (PID: {pid})" if pid else "🔴 已停止"
        await query.edit_message_text(f"🗂 **Alist 面板**\n状态: {status_text}", reply_markup=get_alist_keyboard(bool(pid)), parse_mode='Markdown')
    elif data == "btn_alist_start":
        if not get_alist_pid():
             subprocess.Popen(["alist", "server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
             await asyncio.sleep(2)
        pid = get_alist_pid()
        await query.edit_message_text(f"🗂 **Alist 面板**\n状态: {'✅ 运行中' if pid else '❌ 启动失败'}", reply_markup=get_alist_keyboard(bool(pid)), parse_mode='Markdown')
    elif data == "btn_alist_stop":
        pid = get_alist_pid()
        if pid:
            os.kill(pid, signal.SIGTERM)
            await asyncio.sleep(1)
        pid = get_alist_pid()
        await query.edit_message_text(f"🗂 **Alist 面板**\n状态: {'✅ 运行中' if pid else '🔴 已停止'}", reply_markup=get_alist_keyboard(bool(pid)), parse_mode='Markdown')
    elif data == "btn_alist_info":
        local_ip = get_local_ip()
        await context.bot.send_message(
            chat_id=user_id, 
            text=f"🌐 **Alist 访问地址**:\n\n📡 **局域网**: `http://{local_ip}:5244`\n(适合同一WiFi下的其他设备)\n\n📱 **本机**: `http://127.0.0.1:5244`\n(仅限 Termux 本机访问)", 
            parse_mode='Markdown'
        )
    elif data == "btn_alist_admin":
        try:
            res = subprocess.check_output(["alist", "admin"], text=True).strip()
            await context.bot.send_message(chat_id=user_id, text=f"🔐 信息:\n`{res}`", parse_mode='Markdown')
        except:
            await context.bot.send_message(chat_id=user_id, text="❌ 获取失败")
    elif data == "btn_stream_help":
         config = load_config()
         current_rtmp = config.get('rtmp', '❌ 未设置')
         if current_rtmp != '❌ 未设置':
             # 遮挡部分密钥
             current_rtmp = current_rtmp[:15] + "..." + current_rtmp[-5:]

         await query.edit_message_text(
             "📡 **推流指南**\n\n"
             f"🛠 **当前默认 RTMP**:\n`{current_rtmp}`\n\n"
             "1️⃣ **设置默认推流地址**:\n"
             "`/setrtmp rtmp://...`\n"
             "(设置后，推流只需输入文件路径)\n\n"
             "2️⃣ **开始推流**:\n"
             "• 使用默认地址: `/stream /电影/test.mp4`\n"
             "• 临时指定地址: `/stream /电影/test.mp4 rtmp://...`\n\n"
             "⚠️ 路径支持空格和中文", 
             reply_markup=get_back_keyboard(), 
             parse_mode='Markdown'
         )
    elif data == "btn_update":
         await query.edit_message_text("♻️ 正在检查更新...", parse_mode='Markdown')
         subprocess.Popen("git pull && bash setup.sh", shell=True)


# --- 命令处理 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    print(f"➡️ 收到 /start 命令，来自用户: {user_id}")
    
    if is_owner(user_id):
        print("✅ 验证通过，发送菜单")
        await update.message.reply_text(
            f"👑 **Termux 控制台**\n当前用户: `{user_id}`",
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown'
        )
    else:
        print(f"❌ 验证失败，目标ID: {OWNER_ID}")
        await update.message.reply_text(
            f"🚫 **未授权**\n您的ID: `{user_id}`\n配置ID: `{OWNER_ID}`\n请修改 bot.py",
            parse_mode='Markdown'
        )

async def set_rtmp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """设置 RTMP 默认地址"""
    if not is_owner(update.effective_user.id): return
    
    if not context.args:
        await update.message.reply_text("❌ 用法: `/setrtmp <RTMP地址>`", parse_mode='Markdown')
        return

    rtmp_url = context.args[0]
    config = load_config()
    config['rtmp'] = rtmp_url
    save_config(config)
    
    await update.message.reply_text(f"✅ **RTMP 地址已保存**！\n\n以后可以直接使用 `/stream <路径>` 推流。", parse_mode='Markdown')

async def start_stream(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    global ffmpeg_process
    if ffmpeg_process and ffmpeg_process.poll() is None:
        await update.message.reply_text("⚠️ 已有推流在运行")
        return
    
    if len(context.args) == 0:
        await update.message.reply_text(
            "用法: `/stream <Alist路径> [RTMP地址]`\n"
            "例如: `/stream /电影/video.mp4`", 
            parse_mode='Markdown'
        )
        return

    # 逻辑判断：是使用默认 RTMP 还是 临时 RTMP
    config = load_config()
    saved_rtmp = config.get('rtmp')
    
    rtmp = None
    raw_src = ""

    # 情况1: 只输入了路径 -> 尝试使用保存的 RTMP
    if len(context.args) >= 1:
        # 假设最后一个参数不是 RTMP 协议头，则认为是路径的一部分（用户想用默认配置）
        # 或者用户输入了两个参数，我们先尝试判断
        last_arg = context.args[-1]
        
        if "rtmp://" in last_arg or "rtmps://" in last_arg:
            # 用户显式提供了 RTMP
            rtmp = last_arg
            raw_src = " ".join(context.args[:-1]).strip()
        else:
            # 用户没提供 RTMP，使用保存的
            if saved_rtmp:
                rtmp = saved_rtmp
                raw_src = " ".join(context.args).strip()
            else:
                await update.message.reply_text("❌ 未设置默认 RTMP 地址，且未在命令中提供。\n请先使用 `/setrtmp <url>` 设置，或在命令末尾加上地址。", parse_mode='Markdown')
                return
    
    if not raw_src:
         await update.message.reply_text("❌ 文件路径为空", parse_mode='Markdown')
         return

    src = raw_src
    # 如果是 Alist 路径（以 / 开头），则构造本地 HTTP 链接
    if src.startswith("/"):
        # URL 编码，处理空格和中文，但保留路径分隔符 /
        encoded_src = quote(src, safe='/')
        src = f"http://127.0.0.1:5244{encoded_src}"
    
    # 遮挡显示的 RTMP
    display_rtmp = rtmp[:10] + "..." if rtmp else "Unknown"

    await update.message.reply_text(f"🚀 **启动直连推流**...\n\n📄 **文件**: `{raw_src}`\n🔗 **流地址**: `{src}`\n📡 **推流目标**: `{display_rtmp}`", parse_mode='Markdown')
    
    # FFmpeg 命令
    cmd = [
        "ffmpeg", 
        "-re", 
        "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
        "-i", src, 
        "-c:v", "libx264", "-preset", "ultrafast", "-g", "60",
        "-c:a", "aac", "-ar", "44100", "-b:a", "128k", 
        "-f", "flv", 
        rtmp
    ]
    
    try:
        ffmpeg_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await update.message.reply_text(f"✅ 推流进程已启动 (PID: {ffmpeg_process.pid})")
    except Exception as e:
        await update.message.reply_text(f"❌ 启动失败: {e}")

async def stop_stream(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    global ffmpeg_process
    if ffmpeg_process:
        ffmpeg_process.terminate()
        ffmpeg_process = None
        await update.message.reply_text("🛑 已停止")
    else:
        await update.message.reply_text("⚠️ 无运行中的推流")

def main():
    print(f"🚀 机器人启动中...")
    print(f"📍 当前配置 OWNER_ID: {OWNER_ID}")
    
    if TOKEN == "YOUR_BOT_TOKEN_HERE" or not TOKEN:
        print("❌ 错误: TOKEN 未配置！请编辑 bot.py")
        return

    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stream", start_stream))
    application.add_handler(CommandHandler("stopstream", stop_stream))
    application.add_handler(CommandHandler("setrtmp", set_rtmp))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ Polling 开始... (按 Ctrl+C 停止)")
    application.run_polling()

if __name__ == '__main__':
    main()
