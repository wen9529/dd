import asyncio
import subprocess
import os
import logging
from urllib.parse import quote
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from .config import load_config, FFMPEG_LOG_FILE
from .alist import resolve_alist_path

logger = logging.getLogger("Stream")

# 全局变量用于存储 FFmpeg 进程
ffmpeg_process = None

def kill_zombie_processes():
    """启动时清除残留的 FFmpeg 和 Aria2 进程"""
    try:
        # 在 Termux 中，pkill 是有效的，且不会报错
        subprocess.run(["pkill", "ffmpeg"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "aria2c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass

def get_stream_status():
    global ffmpeg_process
    return ffmpeg_process is not None and ffmpeg_process.poll() is None

def stop_ffmpeg_process():
    global ffmpeg_process
    if ffmpeg_process:
        ffmpeg_process.terminate()
        try:
            ffmpeg_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            ffmpeg_process.kill()
        ffmpeg_process = None
        return True
    return False

def get_log_content(max_chars=1500):
    content = "暂无日志"
    try:
         if os.path.exists(FFMPEG_LOG_FILE):
             with open(FFMPEG_LOG_FILE, "r", encoding='utf-8', errors='ignore') as f:
                 f.seek(0, os.SEEK_END)
                 file_size = f.tell()
                 seek_point = max(0, file_size - max_chars * 2) 
                 f.seek(seek_point)
                 content = f.read()[-max_chars:]
         else:
             content = "日志文件尚未创建。"
    except Exception as e:
         content = f"读取失败: {e}"
    
    if not content.strip():
        content = "日志为空 (FFmpeg 可能刚启动或未输出错误)。"
    return content

async def run_ffmpeg_stream(update: Update, raw_src: str, custom_rtmp: str = None, background_image=None):
    """执行推流逻辑"""
    global ffmpeg_process
    
    message = update.effective_message
    if not message and update.callback_query:
        message = update.callback_query.message

    if get_stream_status():
        if message:
            await message.reply_text("⚠️ **推流正在进行中**\n请先使用 `/stopstream` 停止当前任务。", parse_mode='Markdown')
        return

    # --- 获取配置 ---
    config = load_config()
    server = config.get('rtmp_server', '')
    stream_keys = config.get('stream_keys', [])
    active_index = config.get('active_key_index', 0)
    
    # 高级推流参数 (从 .env 读取)
    stream_width = config.get('stream_width', 1280)
    stream_height = config.get('stream_height', 720)
    stream_fps = config.get('stream_fps', 25)
    stream_preset = config.get('stream_preset', 'veryfast')
    stream_bitrate = config.get('stream_bitrate', '2000k')
    
    alist_host = config.get('alist_host', "http://127.0.0.1:5244")

    key = ""
    current_key_name = "未命名"
    if stream_keys and 0 <= active_index < len(stream_keys):
        key = stream_keys[active_index]['key']
        current_key_name = stream_keys[active_index]['name']
    
    rtmp_url = custom_rtmp if custom_rtmp else (server + key if server and key else config.get('rtmp', ''))
        
    if not rtmp_url:
        if message:
            await message.reply_text("❌ **推流地址无效**\n请检查 [📺 推流设置]。", parse_mode='Markdown')
        return

    # --- 处理文件路径 ---
    src = raw_src.strip()
    is_local_file = os.path.exists(src)
    resolved_via_api = False
    
    # 智能判断 Alist 路径
    if not is_local_file and not src.startswith("http") and not src.startswith("rtmp"):
        # 尝试通过 API 解析真实链接 (解决 401 和重定向问题)
        try:
            loop = asyncio.get_running_loop()
            real_url = await loop.run_in_executor(None, lambda: resolve_alist_path(src))
            
            if real_url:
                src = real_url
                resolved_via_api = True
                logger.info("Alist path resolved successfully via API.")
            else:
                # Fallback to old /d/ method
                encoded_src = quote(src, safe='/')
                src = f"{alist_host}/d{encoded_src}"
                logger.warning("Failed to resolve path, using fallback /d/ url.")
        except Exception as e:
            logger.error(f"Path resolution error: {e}")
            encoded_src = quote(src, safe='/')
            src = f"{alist_host}/d{encoded_src}"
    
    # --- 模式判断 ---
    display_rtmp = rtmp_url[:20] + "..." + rtmp_url[-5:] if len(rtmp_url) > 30 else rtmp_url
    is_slideshow = isinstance(background_image, list) and len(background_image) > 0
    is_single_image = isinstance(background_image, str) and background_image
    
    mode_text = "未知模式"
    if is_slideshow:
        mode_text = f"🎵 音频+轮播 ({len(background_image)}图)"
    elif is_single_image:
        mode_text = "🎵 音频+单图"
    elif is_local_file:
        mode_text = "💿 本地视频"
    else:
        mode_text = "🌐 网络流/Alist"

    status_msg = None
    if message:
        status_msg = await message.reply_text(
            f"🚀 启动推流 ({stream_width}x{stream_height}@{stream_fps}fps)...\n\n"
            f"📄 {os.path.basename(raw_src)}\n"
            f"🔑 {current_key_name}\n"
            f"📡 {display_rtmp}\n"
            f"🛠 {mode_text}"
        )

    # --- 构建命令 ---
    # 基础命令
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    
    if is_local_file:
        cmd.append("-re")
    else:
        # Header 逻辑优化:
        # 1. 如果是 API 解析出的外部链接 (signed url)，通常不需要 Auth Header，避免干扰 (400 Bad Request)
        # 2. 如果是 fallback 的 /d/ 链接，或者解析后依然是 alist host，则添加 Token
        
        need_auth = False
        if not resolved_via_api:
            need_auth = True
        elif alist_host in src:
            need_auth = True
            
        if need_auth:
            alist_token = config.get('alist_token', '')
            if alist_token:
                cmd.extend(["-headers", f"Authorization: {alist_token}\r\nUser-Agent: TermuxBot\r\n"])
            else:
                cmd.extend(["-user_agent", "TermuxBot"])
        else:
            # 外部链接只加 UA
            cmd.extend(["-user_agent", "TermuxBot"])
        
        cmd.extend([
            "-reconnect", "1", "-reconnect_at_eof", "1", 
            "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
            "-rw_timeout", "15000000"
        ])

    # --- 场景分歧 (动态画质) ---

    # 滤镜：动态分辨率缩放
    SCALE_FILTER = f"scale={stream_width}:{stream_height}:force_original_aspect_ratio=decrease,pad={stream_width}:{stream_height}:(ow-iw)/2:(oh-ih)/2"

    if is_slideshow:
        # === 轮播模式 ===
        list_file = os.path.abspath("slideshow_list.txt")
        try:
            target_duration = 20000 
            img_duration = 10 
            loops_needed = int(target_duration / (len(background_image) * img_duration)) + 1
            
            with open(list_file, "w", encoding='utf-8') as f:
                for _ in range(loops_needed):
                    for img_path in background_image:
                        safe_path = img_path.replace("'", "'\\''")
                        f.write(f"file '{safe_path}'\n")
                        f.write(f"duration {img_duration}\n")
                if background_image:
                     safe_path = background_image[-1].replace("'", "'\\''")
                     f.write(f"file '{safe_path}'\n")
        except Exception as e:
            if status_msg: await status_msg.edit_text(f"❌ 列表生成失败: {e}")
            return

        cmd.extend([
            "-f", "concat", "-safe", "0", "-i", list_file, # [0] 视频流
            "-i", src,                                     # [1] 音频流
            
            "-map", "0:v:0",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
            "-pix_fmt", "yuv420p",
            "-vf", f"{SCALE_FILTER},fps={stream_fps}", 
            "-g", str(stream_fps * 2), 
            "-b:v", "1000k", "-maxrate", "1500k", "-bufsize", "2000k",

            "-map", "1:a:0",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k",
            "-shortest"
        ])

    elif is_single_image:
        # === 单图模式 ===
        cmd.extend([
            "-loop", "1", "-framerate", str(stream_fps), "-i", background_image, # [0]
            "-i", src,                                                # [1]
            
            "-map", "0:v:0",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
            "-pix_fmt", "yuv420p",
            "-vf", f"{SCALE_FILTER},format=yuv420p",
            "-g", str(stream_fps * 2),
            "-b:v", "800k", "-maxrate", "1200k", "-bufsize", "2000k",

            "-map", "1:a:0",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k",
            "-shortest"
        ])

    else:
        # === 纯视频模式 ===
        cmd.append("-i")
        cmd.append(src)
        
        cmd.extend([
            "-c:v", "libx264", "-preset", stream_preset,
            # 如果原视频不是 16:9，也会加黑边，保持专业感
            "-vf", f"{SCALE_FILTER},format=yuv420p",
            "-g", str(stream_fps * 2),
            "-b:v", stream_bitrate, "-maxrate", stream_bitrate, "-bufsize", str(int(stream_bitrate.replace('k',''))*2)+'k',
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k"
        ])

    # --- 输出部分 ---
    cmd.extend([
        "-f", "flv", 
        "-flvflags", "no_duration_filesize", 
        rtmp_url
    ])

    log_file = None
    try:
        log_file = open(FFMPEG_LOG_FILE, "w", encoding='utf-8')
        ffmpeg_process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
        log_file.close()
        log_file = None 
        
        await asyncio.sleep(4)
        
        if ffmpeg_process.poll() is not None:
            error_log = get_log_content(800)
            if status_msg:
                await status_msg.edit_text(f"❌ 推流启动失败 (Exit Code: {ffmpeg_process.poll()})")
                await message.reply_text(f"🔍 错误日志:\n{error_log}")
            ffmpeg_process = None
        else:
            keyboard = InlineKeyboardMarkup([
                 [InlineKeyboardButton("📜 实时日志", callback_data="btn_view_log")],
                 [InlineKeyboardButton("🛑 停止推流", callback_data="btn_stop_stream_quick")]
             ])
            
            if status_msg:
                await status_msg.edit_text(
                    f"✅ 推流运行中\n"
                    f"PID: {ffmpeg_process.pid}\n"
                    f"模式: {mode_text}\n"
                    f"画质: {stream_width}x{stream_height} (自适应)\n\n"
                    f"💡 请确保推流码已正确配置。",
                    reply_markup=keyboard
                )

    except Exception as e:
        if log_file:
            try: log_file.close()
            except: pass
        ffmpeg_process = None
        msg = f"❌ 系统异常: {str(e)}"
        if status_msg: await status_msg.edit_text(msg)
        else: await message.reply_text(msg)
