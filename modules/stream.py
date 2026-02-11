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
                 # 读取最后的部分
                 f.seek(0, os.SEEK_END)
                 file_size = f.tell()
                 seek_point = max(0, file_size - max_chars * 2) # 读取稍多一点以防 encoding 问题
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

    if get_stream_status():
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
        await message.reply_text("❌ **推流地址无效**\n请检查 [📺 推流设置]。", parse_mode='Markdown')
        return

    # --- 处理文件路径 ---
    src = raw_src.strip()
    is_local_file = os.path.exists(src)
    
    if not is_local_file and src.startswith("/"):
        # Alist 路径处理
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
        mode_text = "🌐 网络/Alist"

    # 移除 Markdown 防止文件名包含特殊字符导致发送失败
    status_msg = await message.reply_text(
        f"🚀 正在启动进程...\n\n"
        f"📄 {os.path.basename(src)}\n"
        f"🔑 {current_key_name}\n"
        f"📡 {display_rtmp}\n"
        f"🛠 {mode_text}"
    )

    # --- 构建命令 ---
    cmd = ["ffmpeg", "-y", "-hide_banner", "-threads", "4"]
    
    # Alist / Network Headers
    if not is_local_file:
        alist_token = config.get('alist_token', '')
        if alist_token:
            cmd.extend(["-headers", f"Authorization: {alist_token}\r\nUser-Agent: TermuxBot\r\n"])
        else:
            cmd.extend(["-user_agent", "TermuxBot"])
        
        cmd.extend([
            "-reconnect", "1", "-reconnect_at_eof", "1", 
            "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
            "-rw_timeout", "15000000", "-probesize", "10M", "-analyzeduration", "10M"
        ])

    if is_slideshow:
        # 多图轮播
        list_file = os.path.abspath("slideshow_list.txt")
        try:
            with open(list_file, "w", encoding='utf-8') as f:
                for img_path in background_image:
                    safe_path = img_path.replace("'", "'\\''")
                    f.write(f"file '{safe_path}'\n")
                    f.write(f"duration 10\n")
                if background_image:
                     safe_path = background_image[-1].replace("'", "'\\''")
                     f.write(f"file '{safe_path}'\n")
        except Exception as e:
            await status_msg.edit_text(f"❌ 生成列表失败: {e}")
            return

        cmd.extend([
            # 1. 图片输入：无 -re，无限循环
            "-stream_loop", "-1", 
            "-f", "concat", "-safe", "0", "-i", list_file, 
            
            # 2. 音频输入：-re 控制速度
            "-re", "-i", src,
            
            "-map", "0:v:0", "-map", "1:a:0",
            
            # 3. 编码参数：大幅降低码率，移除 stillimage，强制 fps
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            # 关键：在滤镜中强制 fps=15 和 pixel format
            "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=15,format=yuv420p",
            "-g", "30",
            "-b:v", "1000k", "-maxrate", "1500k", "-bufsize", "3000k",
            
            "-c:a", "aac", "-ar", "44100", "-b:a", "128k",
            "-shortest", 
            "-max_muxing_queue_size", "4096"
        ])

    elif is_single_image:
        # 单图
        cmd.extend([
            # 1. 图片输入：移除 -re
            "-loop", "1", "-framerate", "15", "-i", background_image, 
            
            # 2. 音频输入：添加 -re
            "-re", "-i", src,
            
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-vf", "scale='min(1280,iw)':-2,scale='trunc(iw/2)*2':'trunc(ih/2)*2',fps=15,format=yuv420p",
            "-g", "30", "-b:v", "1000k", "-maxrate", "1500k", "-bufsize", "3000k",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest"
        ])

    else:
        # 视频模式 (保持原样)
        cmd.extend([
            "-re", "-i", src,
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-b:v", "2500k", "-maxrate", "3000k", "-bufsize", "6000k",
            "-g", "60", "-c:a", "aac", "-b:a", "128k"
        ])

    # 输出
    cmd.extend(["-f", "flv", "-flvflags", "no_duration_filesize", rtmp_url])

    # --- 启动进程 ---
    log_file = None
    try:
        log_file = open(FFMPEG_LOG_FILE, "w", encoding='utf-8')
        ffmpeg_process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
        
        # 立即关闭父进程的文件句柄，避免泄漏
        log_file.close()
        log_file = None 
        
        # 等待初始化
        await asyncio.sleep(3)
        
        # 检查是否立即退出
        if ffmpeg_process.poll() is not None:
            # --- 失败处理 ---
            error_log = get_log_content(800)
            await status_msg.edit_text(f"❌ 推流启动失败 (Exit Code: {ffmpeg_process.poll()})")
            await message.reply_text(f"🔍 错误日志:\n{error_log}")
            ffmpeg_process = None
        else:
            # --- 成功处理 ---
            keyboard = InlineKeyboardMarkup([
                 [InlineKeyboardButton("📜 实时日志", callback_data="btn_view_log")],
                 [InlineKeyboardButton("🛑 停止推流", callback_data="btn_stop_stream_quick")]
             ])
            
            await status_msg.edit_text(
                f"✅ 推流已稳定运行\n"
                f"PID: {ffmpeg_process.pid}\n"
                f"模式: {mode_text}\n\n"
                f"💡 画面约需 5-10秒 缓冲，请耐心等待。",
                reply_markup=keyboard
            )

    except Exception as e:
        if log_file:
            try:
                log_file.close()
            except:
                pass
        ffmpeg_process = None
        await status_msg.edit_text(f"❌ 系统异常: {str(e)}")
