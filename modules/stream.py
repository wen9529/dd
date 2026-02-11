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
        mode_text = "🌐 网络/Alist"

    status_msg = None
    if message:
        status_msg = await message.reply_text(
            f"🚀 启动稳定模式 (CBR/20fps)...\n\n"
            f"📄 {os.path.basename(src)}\n"
            f"🔑 {current_key_name}\n"
            f"📡 {display_rtmp}\n"
            f"🛠 {mode_text}"
        )

    # --- 构建命令 ---
    cmd = ["ffmpeg", "-y", "-hide_banner"]
    
    # 网络优化参数 - 增加初始连接超时
    if not is_local_file:
        alist_token = config.get('alist_token', '')
        if alist_token:
            cmd.extend(["-headers", f"Authorization: {alist_token}\r\nUser-Agent: TermuxBot\r\n"])
        else:
            cmd.extend(["-user_agent", "TermuxBot"])
        
        cmd.extend([
            "-reconnect", "1", "-reconnect_at_eof", "1", 
            "-reconnect_streamed", "1", "-reconnect_delay_max", "10",
            "-rw_timeout", "20000000", "-probesize", "50M", "-analyzeduration", "50M"
        ])

    # --- 稳定模式核心参数 ---
    # 分辨率: 426x240 (240p)
    # 帧率: 20 fps (标准流畅度，减少超时)
    # GOP: 40 (严格 2秒)
    
    target_w, target_h = 426, 240
    fps_val = "20"
    gop_val = "40" # 2s at 20fps
    scale_filter_str = f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2"

    # 通用编码选项 (Strict CBR)
    x264_opts = [
        "-c:v", "libx264", 
        "-preset", "veryfast", # 稍微提高压缩效率，节省带宽
        "-tune", "zerolatency", 
        "-profile:v", "baseline",
        "-level", "3.0",
        "-sc_threshold", "0" # 关键：禁止场景切换插入关键帧，强制严格 GOP
    ]

    # 通用音频选项 (Lower Bitrate)
    audio_opts = [
        "-c:a", "aac", 
        "-ar", "44100", 
        "-ac", "2", 
        "-b:a", "64k" # 降低音频码率，减轻 Broken Pipe 概率
    ]

    if is_slideshow:
        list_file = os.path.abspath("slideshow_list.txt")
        try:
            target_duration = 14400 
            img_count = len(background_image)
            img_duration = 10 
            
            total_cycle_time = img_count * img_duration
            loops_needed = int(target_duration / total_cycle_time) + 1
            
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
            if status_msg: await status_msg.edit_text(f"❌ 生成列表失败: {e}")
            return

        cmd.extend([
            "-f", "concat", "-safe", "0", "-i", list_file, 
            "-re", "-i", src,
            "-map", "0:v:0", "-map", "1:a:0"
        ])
        
        cmd.extend(x264_opts)
        cmd.extend([
            "-vf", f"{scale_filter_str},fps={fps_val},format=yuv420p",
            "-g", gop_val, 
            # 强制 CBR
            "-b:v", "400k", "-minrate", "400k", "-maxrate", "400k", "-bufsize", "800k",
        ])
        cmd.extend(audio_opts)
        cmd.extend(["-shortest", "-max_muxing_queue_size", "2048"])

    elif is_single_image:
        temp_bg = "temp_bg_240p.jpg"
        final_bg = background_image
        pre_process_success = False
        
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", background_image,
                "-vf", scale_filter_str,
                temp_bg
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            final_bg = temp_bg
            pre_process_success = True
        except Exception as e:
            print(f"Image preprocess failed: {e}")

        vf_filter = "format=yuv420p" if pre_process_success else f"{scale_filter_str},format=yuv420p"

        cmd.extend([
            "-loop", "1", "-framerate", fps_val, "-i", final_bg,
            "-re", "-i", src,
            "-map", "0:v:0", "-map", "1:a:0"
        ])
        
        cmd.extend(x264_opts)
        cmd.extend([
            "-vf", vf_filter,
            "-g", gop_val,
            "-r", fps_val,
            # 强制 CBR
            "-b:v", "350k", "-minrate", "350k", "-maxrate", "350k", "-bufsize", "700k",
        ])
        cmd.extend(audio_opts)
        cmd.extend(["-shortest", "-max_muxing_queue_size", "2048"])

    else:
        # 视频模式
        cmd.extend([
            "-re", "-i", src
        ])
        cmd.extend(x264_opts)
        cmd.extend([
            # 强制 CBR (视频模式稍高一点)
            "-b:v", "600k", "-minrate", "600k", "-maxrate", "600k", "-bufsize", "1200k",
            "-g", "60", # 3s GOP for video
            "-vf", "scale='min(854,iw)':'-2',format=yuv420p"
        ])
        cmd.extend(audio_opts)

    cmd.extend([
        "-f", "flv", 
        "-flvflags", "no_duration_filesize", 
        "-max_interleave_delta", "0", 
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
                    f"配置: 240p / 20fps / CBR模式\n\n"
                    f"💡 启用了严格恒定码率以防止断流。",
                    reply_markup=keyboard
                )

    except Exception as e:
        if log_file:
            try: log_file.close()
            except: pass
        ffmpeg_process = None
        if status_msg: await status_msg.edit_text(f"❌ 系统异常: {str(e)}")
        else: await message.reply_text(f"❌ 系统异常: {str(e)}")
