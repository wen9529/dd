import logging
import asyncio
import subprocess
import os
import signal
import psutil
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# --- ⚠️ 核心配置区域 ⚠️ ---
# 您执行了 reset，配置可能已丢失。
# 请在此处填入您的 Token 和 ID，或者在 Web 界面/本地编辑器修改。
TOKEN = "7565918204:AAH3E3Bb9Op7Xv-kezL6GISeJj8mA6Ycwug" 
OWNER_ID = 1878794912
# -------------------------

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

def get_env_report():
    """生成环境报告文本"""
    ffmpeg_ver = check_program("ffmpeg")
    alist_ver = check_program("alist")
    alist_pid = get_alist_pid()
    ffmpeg_running = ffmpeg_process is not None and ffmpeg_process.poll() is None
    
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
        await context.bot.send_message(chat_id=user_id, text="🌐 地址: `http://127.0.0.1:5244`", parse_mode='Markdown')
    elif data == "btn_alist_admin":
        try:
            res = subprocess.check_output(["alist", "admin"], text=True).strip()
            await context.bot.send_message(chat_id=user_id, text=f"🔐 信息:\n`{res}`", parse_mode='Markdown')
        except:
            await context.bot.send_message(chat_id=user_id, text="❌ 获取失败")
    elif data == "btn_stream_help":
         await query.edit_message_text("用法: `/stream <路径> <RTMP>`", reply_markup=get_back_keyboard(), parse_mode='Markdown')
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

async def start_stream(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    global ffmpeg_process
    if ffmpeg_process and ffmpeg_process.poll() is None:
        await update.message.reply_text("⚠️ 已有推流在运行")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("用法: `/stream <文件> <RTMP>`", parse_mode='Markdown')
        return

    src, rtmp = context.args[0], context.args[1]
    if src.startswith("/"):
        src = f"http://127.0.0.1:5244{src}"
    
    await update.message.reply_text(f"🚀 启动推流...\n源: {src}")
    cmd = ["ffmpeg", "-re", "-i", src, "-c:v", "libx264", "-preset", "ultrafast", "-f", "flv", rtmp]
    try:
        ffmpeg_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await update.message.reply_text(f"✅ PID: {ffmpeg_process.pid}")
    except Exception as e:
        await update.message.reply_text(f"❌ 错误: {e}")

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
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ Polling 开始... (按 Ctrl+C 停止)")
    application.run_polling()

if __name__ == '__main__':
    main()
