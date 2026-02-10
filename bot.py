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
        # print(f"✅ [权限通过] 用户 {uid_str} 正在操作")
        pass
    else:
        print(f"❌ [权限拒绝] 用户 {uid_str} 尝试操作，但管理员ID设定为 {owner_str}")
        
    return is_match

# --- 配置管理 ---
def load_config():
    """加载配置文件，如果文件不存在则使用硬编码配置"""
    config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
    
    # 优先使用 Config 文件中的，如果没有则使用全局变量
    return {
        'token': config.get('token', TOKEN),
        'owner_id': config.get('owner_id', OWNER_ID),
        'rtmp': config.get('rtmp', None), # 兼容旧配置
        'rtmp_server': config.get('rtmp_server', ''),
        'stream_key': config.get('stream_key', '')
    }

def save_config(config_update):
    """保存配置文件"""
    try:
        # 读取现有配置以保留其他字段
        current_config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                current_config = json.load(f)
        
        current_config.update(config_update)
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(current_config, f, indent=4)
        logger.info("配置已保存")
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
    """获取本机局域网 IP"""
    try:
        interfaces = psutil.net_if_addrs()
        priority_interfaces = ['wlan0', 'eth0', 'wlan1']
        for iface in priority_interfaces:
            if iface in interfaces:
                for snic in interfaces[iface]:
                    if snic.family == socket.AF_INET:
                        return snic.address
        exclude_prefixes = ('tun', 'ppp', 'lo', 'docker', 'veth', 'rmnet')
        for name, snics in interfaces.items():
            if name.lower().startswith(exclude_prefixes): continue
            for snic in snics:
                if snic.family == socket.AF_INET and not snic.address.startswith("127."):
                    return snic.address
        return "127.0.0.1"
    except Exception:
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
        f"🌐 **局域网IP**: `{local_ip}`\n\n"
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
        [InlineKeyboardButton("🗂 Alist 管理", callback_data="btn_alist"), InlineKeyboardButton("📺 推流设置", callback_data="btn_stream_settings")],
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

def get_stream_settings_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 修改推流地址", callback_data="btn_edit_server"), InlineKeyboardButton("🔑 修改推流密钥", callback_data="btn_edit_key")],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="btn_back_main")]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回主菜单", callback_data="btn_back_main")]])

# --- 回调处理 ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_owner(user_id):
        await query.answer("❌ 无权操作", show_alert=True)
        return

    await query.answer()
    data = query.data

    if data == "btn_refresh" or data == "btn_back_main":
        # 清除输入状态
        context.user_data['state'] = None
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
            text=f"🌐 **Alist 访问地址**:\n\n📡 **局域网**: `http://{local_ip}:5244`\n\n📱 **本机**: `http://127.0.0.1:5244`", 
            parse_mode='Markdown'
        )
    elif data == "btn_alist_admin":
        try:
            res = subprocess.check_output(["alist", "admin"], text=True).strip()
            await context.bot.send_message(chat_id=user_id, text=f"🔐 信息:\n`{res}`", parse_mode='Markdown')
        except:
            await context.bot.send_message(chat_id=user_id, text="❌ 获取失败")
            
    # --- 新增推流设置逻辑 ---
    elif data == "btn_stream_settings":
         config = load_config()
         server = config.get('rtmp_server') or "❌ 未设置"
         key = config.get('stream_key') or "❌ 未设置"
         
         # 遮挡密钥
         display_key = key
         if key != "❌ 未设置" and len(key) > 8:
             display_key = key[:4] + "****" + key[-4:]

         text = (
             "📺 **推流配置面板**\n\n"
             f"🔗 **服务器地址**: \n`{server}`\n\n"
             f"🔑 **推流密钥**: \n`{display_key}`\n\n"
             "👇 点击下方按钮修改，机器人会提示您直接回复。"
         )
         await query.edit_message_text(text, reply_markup=get_stream_settings_keyboard(), parse_mode='Markdown')
         
    elif data == "btn_edit_server":
        context.user_data['state'] = 'waiting_server'
        await query.edit_message_text(
            "✍️ **请直接回复您的 RTMP 服务器地址**：\n\n例如：`rtmp://live-push.bilivideo.com/live-bvc/`\n\n(输入 `cancel` 取消)",
            parse_mode='Markdown'
        )
        
    elif data == "btn_edit_key":
        context.user_data['state'] = 'waiting_key'
        await query.edit_message_text(
            "✍️ **请直接回复您的 推流密钥**：\n\n例如：`?streamname=...` 或纯密钥字符串\n\n(输入 `cancel` 取消)",
            parse_mode='Markdown'
        )

    elif data == "btn_update":
         await query.edit_message_text("♻️ **正在更新系统...**\n\n1. 正在备份当前配置...\n2. 拉取最新代码...\n3. 机器人将自动重启。", parse_mode='Markdown')
         save_config({'token': TOKEN, 'owner_id': OWNER_ID})
         subprocess.Popen("nohup bash setup.sh > update.log 2>&1 &", shell=True)

# --- 消息处理（用于接收输入）---
async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id): return
    
    state = context.user_data.get('state')
    if not state: return # 无状态，忽略普通消息
    
    text = update.message.text.strip()
    
    # 取消操作
    if text.lower() == 'cancel':
        context.user_data['state'] = None
        await update.message.reply_text("🚫 操作已取消。", reply_markup=get_main_keyboard())
        return

    if state == 'waiting_server':
        # 简单的格式校验
        if not text.startswith("rtmp"):
            await update.message.reply_text("⚠️ 地址似乎不正确，建议以 `rtmp://` 开头。\n请重新输入，或输入 `cancel` 取消。")
            return
            
        save_config({'rtmp_server': text})
        await update.message.reply_text(f"✅ **RTMP 服务器地址已更新！**\n`{text}`", parse_mode='Markdown')
        context.user_data['state'] = None
        # 显示设置面板
        await update.message.reply_text("👇 下一步", reply_markup=get_stream_settings_keyboard())
        
    elif state == 'waiting_key':
        save_config({'stream_key': text})
        await update.message.reply_text(f"✅ **推流密钥已更新！**", parse_mode='Markdown')
        context.user_data['state'] = None
        await update.message.reply_text("👇 配置完成", reply_markup=get_stream_settings_keyboard())


# --- 命令处理 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_owner(user_id):
        await update.message.reply_text(
            f"👑 **Termux 控制台**\n当前用户: `{user_id}`",
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(f"🚫 **未授权**")

async def start_stream(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    global ffmpeg_process
    if ffmpeg_process and ffmpeg_process.poll() is None:
        await update.message.reply_text("⚠️ 已有推流在运行")
        return
    
    if len(context.args) == 0:
        await update.message.reply_text("用法: `/stream <Alist文件路径>`\n例如: `/stream /电影/test.mp4`", parse_mode='Markdown')
        return

    # --- 构造推流地址 ---
    config = load_config()
    server = config.get('rtmp_server', '')
    key = config.get('stream_key', '')
    legacy_rtmp = config.get('rtmp', '')
    
    rtmp_url = ""
    
    # 优先使用 Server + Key 组合
    if server and key:
        rtmp_url = server + key
    elif legacy_rtmp:
        rtmp_url = legacy_rtmp
    
    # 允许命令行参数临时覆盖
    if len(context.args) > 1 and "rtmp" in context.args[-1]:
         rtmp_url = context.args[-1]
         raw_src = " ".join(context.args[:-1]).strip()
    else:
         raw_src = " ".join(context.args).strip()

    if not rtmp_url:
        await update.message.reply_text("❌ **未配置推流地址**\n请点击菜单中的 [📺 推流设置] 进行配置。", parse_mode='Markdown')
        return

    # --- 处理源文件 ---
    src = raw_src
    if src.startswith("/"):
        encoded_src = quote(src, safe='/')
        src = f"http://127.0.0.1:5244{encoded_src}"
    
    display_rtmp = rtmp_url[:15] + "..." if len(rtmp_url) > 15 else rtmp_url

    await update.message.reply_text(f"🚀 **启动直连推流**...\n\n📄 **文件**: `{raw_src}`\n🔗 **流地址**: `{src}`\n📡 **目标**: `{display_rtmp}`", parse_mode='Markdown')
    
    # FFmpeg 命令
    cmd = [
        "ffmpeg", 
        "-re", 
        "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
        "-i", src, 
        "-c:v", "libx264", "-preset", "ultrafast", "-g", "60",
        "-c:a", "aac", "-ar", "44100", "-b:a", "128k", 
        "-f", "flv", 
        rtmp_url
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
    config = load_config()
    final_token = config.get('token')
    
    if final_token == "YOUR_BOT_TOKEN_HERE" or not final_token:
        print("❌ 错误: TOKEN 未配置！请编辑 bot.py 或 bot_config.json")
        return

    application = ApplicationBuilder().token(final_token).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stream", start_stream))
    application.add_handler(CommandHandler("stopstream", stop_stream))
    # 注册消息处理器，用于接收用户输入的配置
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ Polling 开始... (按 Ctrl+C 停止)")
    application.run_polling()

if __name__ == '__main__':
    main()
