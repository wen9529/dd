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

async def run_ffmpeg_stream(update: Update, raw_src: str, custom_rtmp: str = None, background_image=None):
    """执行推流逻辑
    Args:
        raw_src: 视频或音频源路径
        custom_rtmp: 自定义 RTMP 地址
        background_image: 静态图片路径 (str) 或图片列表 (List[str])
    """
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
    
    # --- 获取当前激活的密钥 ---
    stream_keys = config.get('stream_keys', [])
    active_index = config.get('active_key_index', 0)
    current_key_name = "未命名"
    key = ""
    
    if stream_keys and 0 <= active_index < len(stream_keys):
        key = stream_keys[active_index]['key']
        current_key_name = stream_keys[active_index]['name']
    
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
        await message.reply_text("❌ **未配置推流地址**\n请先在菜单中点击 [📺 推流设置] -> [🔑 管理密钥] 进行配置。", parse_mode='Markdown')
        return

    # 3. 处理源链接
    src = raw_src.strip()
    is_local_file = False
    
    if os.path.exists(src):
        is_local_file = True
    elif src.startswith("/"):
        encoded_src = quote(src, safe='/')
        src = f"http://127.0.0.1:5244{encoded_src}"
    
    # 4. 判断模式并发送反馈
    display_rtmp = rtmp_url[:25] + "..." if len(rtmp_url) > 25 else rtmp_url
    
    is_slideshow = isinstance(background_image, list) and len(background_image) > 0
    is_single_image = isinstance(background_image, str)
    
    if is_slideshow:
        mode_text = f"🎵 音频+多图轮播 ({len(background_image)}张)"
        img_info = "多张图片"
    elif is_single_image:
        mode_text = "🎵 音频+单图模式"
        img_info = os.path.basename(background_image)
    elif is_local_file:
        mode_text = "💿 本地视频模式"
        img_info = "无"
    else:
        mode_text = "🌐 网络流/Alist模式"
        img_info = "无"
    
    # 显示使用的密钥名称
    key_info = f"🔑 使用密钥: **{current_key_name}**" if key else "🔑 使用旧版完整链接"

    await message.reply_text(
        f"🚀 **启动推流任务** (极速模式)\n\n"
        f"📄 **源**: `{os.path.basename(src)}`\n"
        f"🖼 **图**: `{img_info}`\n"
        f"{key_info}\n"
        f"📡 **目标**: `{display_rtmp}`\n"
        f"{mode_text}\n\n"
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
        "-hide_banner",
    ]
    
    if not is_local_file and not (is_slideshow or is_single_image):
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

    cmd.extend(["-probesize", "10M", "-analyzeduration", "10M"])

    if is_slideshow:
        # --- 多图轮播模式 ---
        # 创建 concat 列表文件
        list_file = "slideshow_list.txt"
        with open(list_file, "w") as f:
            for img_path in background_image:
                # 转义单引号
                safe_path = img_path.replace("'", "'\\''")
                f.write(f"file '{safe_path}'\n")
                f.write(f"duration 5\n") # 每张图显示 5 秒
        
        cmd.extend([
            "-re",                  # 实时读取速度
            "-stream_loop", "-1",   # 循环播放输入
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,        # 输入0: concat列表
            "-i", src,              # 输入1: 音频
            
            # 视频编码
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            # 关键：统一缩放到 1080x1920 (竖屏)，保持比例，背景填充黑边
            # 这样可以防止不同尺寸的图片导致 FFmpeg 崩溃或推流断流
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-g", "20",             
            "-b:v", "1500k",
            "-r", "10",             # 输出 10fps
            
            # 音频编码
            "-c:a", "aac", 
            "-ar", "44100", 
            "-b:a", "128k",
            
            "-shortest"             # 音频结束时停止
        ])
    
    elif is_single_image:
        # --- 单图模式 (保持原有的高效 -loop 1) ---
        cmd.extend([
            "-loop", "1",           
            "-framerate", "10",     
            "-i", background_image, 
            "-re",                  
            "-i", src,              
            
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "stillimage",
            "-pix_fmt", "yuv420p",
            # 同样应用缩放限制，防止单图过大
            "-vf", "scale='min(1920,iw)':-2,scale='trunc(iw/2)*2':'trunc(ih/2)*2'",
            "-g", "20",             
            "-b:v", "1500k",        
            
            "-c:a", "aac", 
            "-ar", "44100", 
            "-b:a", "128k",
            
            "-shortest"             
        ])
    else:
        # --- 纯视频模式 ---
        cmd.extend([
            "-re",
            "-i", src, 
            
            "-c:v", "libx264", 
            "-preset", "ultrafast", 
            "-tune", "zerolatency", 
            "-b:v", "2500k", "-maxrate", "3000k", "-bufsize", "6000k",
            "-pix_fmt", "yuv420p",
            "-g", "30",
            
            "-c:a", "aac", "-ar", "44100", "-b:a", "128k", 
        ])

    # 输出通用参数
    cmd.extend([
        "-f", "flv", 
        "-flvflags", "no_duration_filesize",
        "-rw_timeout", "30000000", 
        rtmp_url
    ])
    
    try:
        log_file = open(FFMPEG_LOG_FILE, "w")
        ffmpeg_process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
        
        await asyncio.sleep(2) 
        
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
             elif "I/O error" in log_content:
                 suggestion = "\n💡 **提示**：检测到 I/O 错误。可能是推流地址有误、网络不通，或 Termux 的 SSL 证书问题。"

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
                 f"模式: {mode_text}\n"
                 f"画面应在 5秒内出现。如果仍黑屏，请检查网络上传带宽。",
                 reply_markup=keyboard,
                 parse_mode='Markdown'
             )
             
    except Exception as e:
        await message.reply_text(f"❌ 启动异常: {e}")
