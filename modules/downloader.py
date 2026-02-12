import asyncio
import os
import logging
import psutil

logger = logging.getLogger("Downloader")

def get_active_downloads():
    """获取正在运行的 aria2c 进程信息"""
    tasks = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
        try:
            if 'aria2c' in proc.info['name']:
                cmdline = proc.info.get('cmdline', [])
                # 尝试从命令行参数中提取 URL 或文件名
                target = "未知任务"
                for arg in cmdline:
                    if arg.startswith("http") or arg.startswith("magnet"):
                        target = arg.split("/")[-1][:30]
                        break
                
                # 计算运行时间
                duration = int(time.time() - proc.info['create_time'])
                
                tasks.append(f"• PID: `{proc.info['pid']}` | ⏳ {duration}s\n  📄 {target}")
        except:
            continue
    return tasks

import time

async def aria2_download_task(url: str, context, chat_id: int):
    """
    执行 Aria2 下载任务，并在完成后通知用户
    """
    download_dir = "/sdcard/Download"
    
    if not os.path.exists(download_dir):
        # 尝试回退到内部存储
        download_dir = os.path.join(os.getcwd(), "downloads")
        os.makedirs(download_dir, exist_ok=True)

    filename_hint = url.split('/')[-1].split('?')[0]
    if len(filename_hint) > 50: filename_hint = filename_hint[:47] + "..."
    if not filename_hint: filename_hint = "未知文件"

    logger.info(f"开始下载: {url}")
    
    try:
        # 构建命令
        cmd = [
            "aria2c", 
            "-d", download_dir,
            "-x", "16", 
            "-s", "16",
            "--seed-time=0",
            "--summary-interval=0",
            # 伪装 User-Agent 防止被某些站点拒绝
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            url
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ **下载完成**\n\n📂 目录: `{download_dir}`\n📄 文件: `{filename_hint}`\n\n提示: 您现在可以在 [☁️ 云盘浏览] -> [/sdcard/Download] 中找到它。",
                parse_mode='Markdown'
            )
        else:
            err_msg = stderr.decode().strip()
            if len(err_msg) > 500: err_msg = err_msg[-500:]
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ **下载失败**\n\n文件: `{filename_hint}`\n错误: `{err_msg}`",
                parse_mode='Markdown'
            )

    except Exception as e:
        logger.error(f"下载异常: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ **系统错误**: {str(e)}"
        )
