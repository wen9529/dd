import asyncio
import subprocess
import os
from urllib.parse import quote
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from .config import load_config, FFMPEG_LOG_FILE

# 全局变量用于存储 FFmpeg 进程
ffmpeg_process = None

def get_stream_status():
    global ffmpeg_process
    return ffmpeg_process is not None and ffmpeg_process.poll() is None

def stop_ffmpeg_process():
    global ffmpeg_process
    if ffmpeg_process:
        ffmpeg_process.terminate()
        ffmpeg_process = None
        return True
    return False

def get_log_content(max_chars=1500):
    content = "暂无日志"
    try:
         with open(FFMPEG_LOG_FILE, "r") as f:
             content = f.read()[-max_chars:]
    except Exception as e:
         content = f"读取失败: {e}"
    if not content.strip():
        content = "日志文件为空，FFmpeg 可能尚未输出任何信息。"
    return content

async def run_ffmpeg_stream(update: Update, raw_src: str, custom_rtmp: str = None):
    """执行推流逻辑"""
    global ffmpeg_process
    
    # 使用 effective_message 以兼容 CommandHandler (update.message) 和 CallbackQueryHandler (update.callback_query.message)
    message = update.effective_message

    # 1. 检查是否已有任务
    if get_stream_status():
        await message.reply_text("⚠️ **推流正在进行中**\n请先使用 `/stopstream` 停止当前任务，或等待其结束。", parse_mode='Markdown')
        return

    # 2. 获取 RTMP 地址
    config = load_config()
    server = config.get('rtmp_server', '')
    key = config.get('stream_key', '')
    legacy_rtmp = config.get('rtmp', '')
    alist_token = config.get('alist_token', '')
    
    rtmp_url = ""
    if custom_rtmp:
        rtmp_url = custom_rtmp
    elif server and key:
        rtmp_url = server + key
    elif legacy_rtmp:
        rtmp_url = legacy_rtmp
        
    if not rtmp_url:
        await message.reply_text("❌ **未配置推流地址**\n请先在菜单中点击 [📺 推流设置] 进行配置，或联系管理员。", parse_mode='Markdown')
        return

    # 3. 处理源链接
    src = raw_src.strip()
    is_local_file = False
    
    if os.path.exists(src):
        is_local_file = True
    elif src.startswith("/"):
        encoded_src = quote(src, safe='/')
        src = f"http://127.0.0.1:5244{encoded_src}"
    
    # 4. 发送反馈
    display_rtmp = rtmp_url[:15] + "..." if len(rtmp_url) > 15 else rtmp_url
    await message.reply_text(
        f"🚀 **启动推流任务**\n\n"
        f"📄 **源**: `{raw_src}`\n"
        f"📡 **目标**: `{display_rtmp}`\n"
        f"{'💿 本地文件模式' if is_local_file else '🌐 网络流/Alist模式'}\n\n"
        "⏳ 正在启动进程...", 
        parse_mode='Markdown'
    )

    # 5. 执行 FFmpeg
    headers_list = [
        "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]
    if alist_token and not is_local_file:
        headers_list.append(f"Authorization: {alist_token}")
        
    headers_str = "".join([h + "\r\n" for h in headers_list])

    cmd = [
        "ffmpeg", 
        "-y",
    ]
    
    if not is_local_file:
        cmd.extend([
            "-headers", headers_str,
            "-reconnect", "1", 
            "-reconnect_at_eof", "1",
            "-reconnect_streamed", "0",
            "-reconnect_on_network_error", "1",
            "-reconnect_on_http_error", "5xx",
            "-reconnect_delay_max", "5",
            "-rw_timeout", "15000000",
        ])

    cmd.extend([
        "-probesize", "50M", 
        "-analyzeduration", "50M",
        "-re",
        "-i", src, 
        "-c:v", "libx264", "-preset", "veryfast", "-g", "60",
        "-c:a", "aac", "-ar", "44100", "-b:a", "128k", 
        "-f", "flv", 
        rtmp_url
    ])
    
    try:
        log_file = open(FFMPEG_LOG_FILE, "w")
        ffmpeg_process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
        
        await asyncio.sleep(3)
        
        if ffmpeg_process.poll() is not None:
             log_file.close()
             
             log_content = "无日志记录"
             try:
                 with open(FFMPEG_LOG_FILE, "r") as f:
                     log_content = f.read()[-1000:]
             except Exception as e:
                 log_content = f"读取日志失败: {e}"

             suggestion = ""
             if "401 Unauthorized" in log_content:
                 suggestion = "\n💡 **修复建议**：检测到 401 认证错误。请尝试在 [🗂 Alist 管理] -> [🔐 设置 Token] 中填入您的 Alist Token。"
             elif "moov atom not found" in log_content:
                 suggestion = "\n💡 **提示**：'moov atom not found' 通常表示文件索引在末尾。已开启 Seek 模式，如果仍失败，请检查源文件是否支持 Range 请求。"

             await message.reply_text(
                 f"❌ **推流启动失败** (进程意外退出)\n\n"
                 f"🔍 **错误详情 (最后日志)**:\n"
                 f"```\n{log_content}\n```"
                 f"{suggestion}", 
                 parse_mode='Markdown'
             )
             ffmpeg_process = None
        else:
             keyboard = InlineKeyboardMarkup([
                 [InlineKeyboardButton("📜 查看实时日志", callback_data="btn_view_log")],
                 [InlineKeyboardButton("🛑 停止推流", callback_data="btn_stop_stream_quick")]
             ])
             await message.reply_text(
                 f"✅ **推流已稳定运行**\n"
                 f"PID: {ffmpeg_process.pid}\n\n"
                 f"如果画面仍未显示，请点击下方 [查看实时日志] 排查问题。",
                 reply_markup=keyboard,
                 parse_mode='Markdown'
             )
             
    except Exception as e:
        await message.reply_text(f"❌ 启动异常: {e}")
