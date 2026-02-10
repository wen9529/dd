import logging
import asyncio
import subprocess
import os
import signal
import psutil
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# --- 硬编码配置区域 ---
TOKEN = "7565918204:AAH3E3Bb9Op7Xv-kezL6GISeJj8mA6Ycwug"
OWNER_ID = 1878794912
# --------------------

# 全局变量用于存储 FFmpeg 进程
ffmpeg_process = None

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def is_owner(user_id):
    return str(user_id) == str(OWNER_ID)

# --- 辅助功能 ---
def check_program(cmd):
    """检查程序版本"""
    try:
        if cmd == "ffmpeg":
            output = subprocess.check_output(["ffmpeg", "-version"], stderr=subprocess.STDOUT, text=True)
            return output.splitlines()[0].split()[2] # 获取版本号
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
        if 'alist' in proc.info['name']:
            return proc.info['pid']
    return None

def get_env_report():
    """生成环境报告文本"""
    ffmpeg_ver = check_program("ffmpeg")
    alist_ver = check_program("alist")
    
    # 检查进程
    alist_pid = get_alist_pid()
    ffmpeg_running = ffmpeg_process is not None and ffmpeg_process.poll() is None
    
    # 系统资源
    cpu_usage = psutil.cpu_percent(interval=None)
    mem_info = psutil.virtual_memory()
    mem_usage = f"{mem_info.used / 1024 / 1024:.0f}MB / {mem_info.total / 1024 / 1024:.0f}MB"

    return (
        f"🖥 **服务器环境报告**\n\n"
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

# --- 键盘菜单定义 ---
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

# --- 按钮回调处理 ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_owner(user_id):
        await query.answer("❌ 无权操作", show_alert=True)
        return

    await query.answer() # 停止加载动画
    data = query.data

    if data == "btn_refresh" or data == "btn_back_main":
        await query.edit_message_text(
            f"👑 **Termux 控制台**\n当前用户: `{user_id}`\n请点击下方按钮进行管理：",
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown'
        )

    elif data == "btn_env":
        report = get_env_report()
        await query.edit_message_text(report, reply_markup=get_back_keyboard(), parse_mode='Markdown')

    elif data == "btn_stream_help":
        msg = (
            "📺 **推流功能说明**\n\n"
            "目前仅支持通过命令操作：\n"
            "1. `/stream <文件> <RTMP地址>` - 开始推流\n"
            "2. `/stopstream` - 停止推流\n\n"
            "✨ **提示**: 文件路径如果以 `/` 开头，会自动补全为本地 Alist 地址。"
        )
        await query.edit_message_text(msg, reply_markup=get_back_keyboard(), parse_mode='Markdown')

    elif data == "btn_alist":
        pid = get_alist_pid()
        status_text = f"✅ Alist 正在运行 (PID: {pid})" if pid else "🔴 Alist 已停止"
        await query.edit_message_text(
            f"🗂 **Alist 管理面板**\n\n状态: {status_text}",
            reply_markup=get_alist_keyboard(bool(pid)),
            parse_mode='Markdown'
        )

    elif data == "btn_alist_start":
        if not get_alist_pid():
             subprocess.Popen(["alist", "server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
             await asyncio.sleep(2) # 等待启动
        
        pid = get_alist_pid()
        status_text = f"✅ Alist 正在运行 (PID: {pid})" if pid else "❌ 启动失败或超时"
        await query.edit_message_text(
            f"🗂 **Alist 管理面板**\n\n状态: {status_text}",
            reply_markup=get_alist_keyboard(bool(pid)),
            parse_mode='Markdown'
        )

    elif data == "btn_alist_stop":
        pid = get_alist_pid()
        if pid:
            os.kill(pid, signal.SIGTERM)
            await asyncio.sleep(1)
        
        pid = get_alist_pid()
        status_text = f"✅ Alist 正在运行 (PID: {pid})" if pid else "🔴 Alist 已停止"
        await query.edit_message_text(
             f"🗂 **Alist 管理面板**\n\n状态: {status_text}",
            reply_markup=get_alist_keyboard(bool(pid)),
            parse_mode='Markdown'
        )

    elif data == "btn_alist_info":
        await context.bot.send_message(chat_id=user_id, text="🌐 **访问地址**:\n\n本地: `http://127.0.0.1:5244`\n(确保设备在同一局域网)", parse_mode='Markdown')
        
    elif data == "btn_alist_admin":
        try:
            result = subprocess.check_output(["alist", "admin"], text=True)
            await context.bot.send_message(chat_id=user_id, text=f"🔐 **管理员信息**:\n```\n{result.strip()}\n```", parse_mode='Markdown')
        except:
             await context.bot.send_message(chat_id=user_id, text="❌ 获取密码失败", parse_mode='Markdown')

    elif data == "btn_update":
        await query.edit_message_text("♻️ 正在连接 Git 仓库检查更新...", parse_mode='Markdown')
        try:
            # 1. 检查更新
            subprocess.run("git fetch", shell=True, check=True)
            local_hash = subprocess.check_output("git rev-parse HEAD", shell=True, text=True).strip()
            remote_hash = subprocess.check_output("git rev-parse @{u}", shell=True, text=True).strip()
            
            if local_hash != remote_hash:
                await context.bot.send_message(chat_id=user_id, text="🚀 **发现新版本！**\n\n正在拉取代码并重启机器人，请稍候...", parse_mode='Markdown')
                # 触发更新脚本，setup.sh 会重启 bot，所以这里 bot 进程会结束
                subprocess.Popen("git pull && bash setup.sh", shell=True)
            else:
                commit_id = local_hash[:7]
                await query.edit_message_text(f"✅ **当前已是最新版本**\n\nCommit: `{commit_id}`\n\n后台自动更新进程(PM2) 也会每分钟自动检查。", reply_markup=get_back_keyboard(), parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"❌ 检查更新失败:\n{str(e)}", reply_markup=get_back_keyboard(), parse_mode='Markdown')


# --- 命令处理 ---
async def check_env(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(命令) 检查服务器环境"""
    if not is_owner(update.effective_user.id): return
    await update.message.reply_text(get_env_report(), parse_mode='Markdown')

async def alist_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(命令) 显示 Alist 管理菜单"""
    if not is_owner(update.effective_user.id): return
    
    pid = get_alist_pid()
    status_text = f"✅ Alist 正在运行 (PID: {pid})" if pid else "🔴 Alist 已停止"
    
    await update.message.reply_text(
        f"🗂 **Alist 管理面板**\n\n状态: {status_text}",
        reply_markup=get_alist_keyboard(bool(pid)),
        parse_mode='Markdown'
    )

# --- FFmpeg 推流功能 (保留原样) ---
async def start_stream(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    global ffmpeg_process
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text("⚠️ **参数错误**\n用法: `/stream <链接/路径> <RTMP地址>`", parse_mode='Markdown')
        return

    if ffmpeg_process and ffmpeg_process.poll() is None:
        await update.message.reply_text("⚠️ 当前已有推流正在进行，请先发送 /stopstream 停止。")
        return

    video_input = args[0]
    rtmp_url = args[1]

    if video_input.startswith("/"):
        if not get_alist_pid():
            await update.message.reply_text("⚠️ Alist 未运行，无法使用本地路径。\n请先在菜单中启动 Alist。")
            return
        video_input = f"http://127.0.0.1:5244{video_input}"
        await update.message.reply_text(f"🔗 已转换为本地 Alist 链接:\n`{video_input}`", parse_mode='Markdown')

    await update.message.reply_text(f"🚀 **准备推流**...\n源: `{video_input}`", parse_mode='Markdown')

    command = ["ffmpeg", "-re", "-i", video_input, "-c:v", "libx264", "-preset", "veryfast", "-maxrate", "3000k", "-bufsize", "6000k", "-pix_fmt", "yuv420p", "-g", "50", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-f", "flv", rtmp_url]

    try:
        ffmpeg_process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await update.message.reply_text(f"✅ **推流已后台启动**\nPID: {ffmpeg_process.pid}\n发送 /stopstream 停止。")
    except Exception as e:
        await update.message.reply_text(f"❌ 启动 FFmpeg 失败: {e}")

async def stop_stream(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    global ffmpeg_process
    if ffmpeg_process and ffmpeg_process.poll() is None:
        ffmpeg_process.terminate()
        try:
            ffmpeg_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            ffmpeg_process.kill()
        ffmpeg_process = None
        await update.message.reply_text("🛑 推流已强制停止。")
    else:
        await update.message.reply_text("⚠️ 当前没有正在进行的推流任务。")

# --- 基础功能 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_owner(user_id):
        await update.message.reply_text(
            f"👑 **Termux 控制台**\n当前用户: `{user_id}`\n请点击下方按钮进行管理：",
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(f"👋 你好，我是 Termux 机器人。\n你的 ID: `{user_id}`\n\n(请将此 ID 填入代码中的 OWNER_ID 字段以获取管理员权限)", parse_mode='Markdown')

def main():
    print(f"🚀 正在启动 Termux 机器人...")
    
    application = ApplicationBuilder().token(TOKEN).build()
    
    # 基础命令
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("env", check_env))
    application.add_handler(CommandHandler("alist", alist_menu))
    application.add_handler(CommandHandler("stream", start_stream))
    application.add_handler(CommandHandler("stopstream", stop_stream))
    
    # 注册按钮回调处理器
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ 机器人运行中...")
    application.run_polling()

if __name__ == '__main__':
    main()
