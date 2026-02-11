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
    
    if not is_local_file and src.startswith("/"):
        encoded_src = quote(src, safe='/')
        src = f"http://127.0.0.1:5244{encoded_src}"
    
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
        mode_text = "🌐 网络流"

    status_msg = None
    if message:
        status_msg = await message.reply_text(
            f"🚀 启动标准推流 (25fps/128k)...\n\n"
            f"📄 {os.path.basename(src)}\n"
            f"🔑 {current_key_name}\n"
            f"📡 {display_rtmp}\n"
            f"🛠 {mode_text}"
        )

    # --- 构建命令 ---
    # 基础命令，-y 覆盖输出，-hide_banner 减少日志
    cmd = ["ffmpeg", "-y", "-hide_banner"]
    
    # 核心差异：本地文件必须用 -re (实时读取)，网络流不需要 (或者依赖 reconnect)
    if is_local_file:
        cmd.append("-re")
    else:
        # 仅针对网络流添加重连参数
        # 对本地文件加这些会导致 "Protocol not found" 或 IO 错误
        alist_token = config.get('alist_token', '')
        if alist_token:
            cmd.extend(["-headers", f"Authorization: {alist_token}\r\nUser-Agent: TermuxBot\r\n"])
        else:
            cmd.extend(["-user_agent", "TermuxBot"])
        
        cmd.extend([
            "-reconnect", "1", "-reconnect_at_eof", "1", 
            "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
            "-rw_timeout", "15000000"
        ])

    # --- 场景分歧 ---

    if is_slideshow:
        # === 轮播模式 ===
        # 这种模式最容易出问题，我们使用最标准的 concat 协议
        list_file = os.path.abspath("slideshow_list.txt")
        try:
            target_duration = 20000 # 足够长即可
            img_duration = 10 
            loops_needed = int(target_duration / (len(background_image) * img_duration)) + 1
            
            with open(list_file, "w", encoding='utf-8') as f:
                for _ in range(loops_needed):
                    for img_path in background_image:
                        safe_path = img_path.replace("'", "'\\''")
                        f.write(f"file '{safe_path}'\n")
                        f.write(f"duration {img_duration}\n")
                # 必须重复最后一张图确保不会黑屏
                if background_image:
                     safe_path = background_image[-1].replace("'", "'\\''")
                     f.write(f"file '{safe_path}'\n")
        except Exception as e:
            if status_msg: await status_msg.edit_text(f"❌ 列表生成失败: {e}")
            return

        cmd.extend([
            "-f", "concat", "-safe", "0", "-i", list_file, # 输入0: 视频/图片流
            "-i", src,                                     # 输入1: 音频流
            
            # 视频编码
            "-map", "0:v:0",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
            "-pix_fmt", "yuv420p",
            "-vf", "scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2,fps=25", # 480p, 25fps 标准
            "-g", "50", # 2秒一个关键帧 (25fps * 2)
            "-b:v", "500k", "-maxrate", "800k", "-bufsize", "1000k",

            # 音频编码 (标准参数)
            "-map", "1:a:0",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k",
            
            "-shortest" # 音频结束即停止
        ])

    elif is_single_image:
        # === 单图模式 ===
        # 使用 -loop 1 是最稳的单图推流方式
        cmd.extend([
            "-loop", "1", "-framerate", "25", "-i", background_image, # 输入0: 循环图片
            "-i", src,                                                # 输入1: 音频流
            
            # 视频编码
            "-map", "0:v:0",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
            "-pix_fmt", "yuv420p",
            "-vf", "scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-g", "50",
            "-b:v", "400k", "-maxrate", "600k", "-bufsize", "800k",

            # 音频编码
            "-map", "1:a:0",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k",
            
            "-shortest"
        ])

    else:
        # === 纯视频模式 (本地或网络) ===
        cmd.append("-i")
        cmd.append(src)
        
        # 视频参数
        # 移除 zerolatency，因为它会禁用缓冲区，导致本地文件读取卡顿
        cmd.extend([
            "-c:v", "libx264", "-preset", "veryfast",
            "-vf", "scale='min(854,iw)':'-2',format=yuv420p", # 保持比例缩放，不强制拉伸
            "-g", "60", # 30fps * 2s
            "-b:v", "1500k", "-maxrate", "2000k", "-bufsize", "3000k"
        ])
        
        # 音频参数
        # 强制转码 AAC，防止源音频格式 (如 flac/opus) 不被 RTMP 支持
        cmd.extend([
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
                    f"配置: 480p / 25fps / 128k音频\n\n"
                    f"💡 已恢复标准配置。",
                    reply_markup=keyboard
                )

    except Exception as e:
        if log_file:
            try: log_file.close()
            except: pass
        ffmpeg_process = None
        if status_msg: await status_msg.edit_text(f"❌ 系统异常: {str(e)}")
        else: await message.reply_text(f"❌ 系统异常: {str(e)}")
