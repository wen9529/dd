import logging
import asyncio
import subprocess
import os
import signal
import psutil
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

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

# --- Alist 管理功能 ---

def get_alist_pid():
    """查找 alist 进程 PID"""
    for proc in psutil.process_iter(['pid', 'name']):
        if 'alist' in proc.info['name']:
            return proc.info['pid']
    return None

async def alist_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示 Alist 管理菜单"""
    if not is_owner(update.effective_user.id):
        return
    
    pid = get_alist_pid()
    status = f"✅ 运行中 (PID: {pid})" if pid else "🔴 已停止"
    
    msg = (
        f"🗂 **Alist 管理面板**\n\n"
        f"状态: {status}\n\n"
        f"指令列表:\n"
        f"/alist_start - 启动服务\n"
        f"/alist_stop - 停止服务\n"
        f"/alist_admin - 查看管理员密码\n"
        f"/alist_info - 查看访问地址"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def alist_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    
    if get_alist_pid():
        await update.message.reply_text("⚠️ Alist 已经在运行中。")
        return

    try:
        # 使用 nohup 后台启动
        subprocess.Popen(["alist", "server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await update.message.reply_text("✅ Alist 启动命令已发送，请稍后检查状态。")
    except Exception as e:
        await update.message.reply_text(f"❌ 启动失败: {e}")

async def alist_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    
    pid = get_alist_pid()
    if pid:
        os.kill(pid, signal.SIGTERM)
        await update.message.reply_text("🛑 Alist 已停止。")
    else:
        await update.message.reply_text("⚠️ Alist 当前未运行。")

async def alist_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    
    try:
        # 运行 alist admin 获取信息
        result = subprocess.check_output(["alist", "admin"], text=True)
        await update.message.reply_text(f"🔐 **Alist 管理员信息**:\n\n`{result.strip()}`", parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ 获取失败: {e}")

async def alist_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌐 **访问地址**:\n\n本地: `http://127.0.0.1:5244`\n(如果在 Termux 运行，请确保手机和访问设备在同一局域网，并使用手机 IP 访问)")

# --- FFmpeg 推流功能 ---

async def start_stream(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    启动推流
    用法: /stream <视频链接> <RTMP推流地址>
    """
    if not is_owner(update.effective_user.id): return
    
    global ffmpeg_process
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text(
            "⚠️ **参数错误**\n\n用法:\n`/stream <视频链接> <RTMP地址>`\n\n"
            "示例:\n`/stream http://127.0.0.1:5244/d/movie.mp4 rtmp://live-push.telegram.org/type/key`",
            parse_mode='Markdown'
        )
        return

    if ffmpeg_process and ffmpeg_process.poll() is None:
        await update.message.reply_text("⚠️ 当前已有推流正在进行，请先发送 /stopstream 停止。")
        return

    video_url = args[0]
    rtmp_url = args[1]

    await update.message.reply_text(f"🚀 **准备推流**...\n\n源: `{video_url}`\n目标: Telegram Live", parse_mode='Markdown')

    # 构建 FFmpeg 命令
    # -re : 按本地帧率读取 (模拟直播)
    # -i : 输入
    # -c:v libx264 : 视频编码 (使用软解兼容性好)
    # -preset veryfast : 编码速度优先，减少延迟
    # -c:a aac : 音频编码
    # -f flv : 输出格式必须为 flv 才能推送到 RTMP
    command = [
        "ffmpeg",
        "-re",
        "-i", video_url,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-maxrate", "3000k",
        "-bufsize", "6000k",
        "-pix_fmt", "yuv420p",
        "-g", "50",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-f", "flv",
        rtmp_url
    ]

    try:
        # 启动 FFmpeg 进程
        ffmpeg_process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        await update.message.reply_text(f"✅ **推流已后台启动**\nPID: {ffmpeg_process.pid}\n发送 /stopstream 停止。")
    except Exception as e:
        await update.message.reply_text(f"❌ 启动 FFmpeg 失败: {e}")

async def stop_stream(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """停止推流"""
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
        msg = (
            f"👑 **Termux 全能机器人**\n\n"
            f"🛠 **Alist 管理**:\n"
            f"/alist - 查看 Alist 面板\n\n"
            f"📺 **直播推流**:\n"
            f"/stream - 开始推流\n"
            f"/stopstream - 停止推流\n\n"
            f"你的 ID: `{user_id}`"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')
    else:
        await update.message.reply_text(f"👋 你好，我是 Termux 机器人。\n你的 ID: `{user_id}`", parse_mode='Markdown')

def main():
    print(f"🚀 正在启动 Termux 机器人...")
    
    application = ApplicationBuilder().token(TOKEN).build()
    
    # 基础命令
    application.add_handler(CommandHandler("start", start))
    
    # Alist 命令
    application.add_handler(CommandHandler("alist", alist_menu))
    application.add_handler(CommandHandler("alist_start", alist_start))
    application.add_handler(CommandHandler("alist_stop", alist_stop))
    application.add_handler(CommandHandler("alist_admin", alist_admin))
    application.add_handler(CommandHandler("alist_info", alist_info))
    
    # 推流命令
    application.add_handler(CommandHandler("stream", start_stream))
    application.add_handler(CommandHandler("stopstream", stop_stream))
    
    print("✅ 机器人运行中...")
    application.run_polling()

if __name__ == '__main__':
    main()
