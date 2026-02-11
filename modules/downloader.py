import asyncio
import os
import logging

logger = logging.getLogger("Downloader")

async def aria2_download_task(url: str, context, chat_id: int):
    """
    执行 Aria2 下载任务，并在完成后通知用户
    """
    download_dir = "/sdcard/Download"
    
    if not os.path.exists(download_dir):
        # 尝试回退到内部存储
        download_dir = os.path.join(os.getcwd(), "downloads")
        os.makedirs(download_dir, exist_ok=True)

    # 简化的文件名获取逻辑 (Aria2 会自动处理，我们主要用于日志)
    filename_hint = url.split('/')[-1].split('?')[0]
    if len(filename_hint) > 50: filename_hint = filename_hint[:47] + "..."
    if not filename_hint: filename_hint = "未知文件"

    logger.info(f"开始下载: {url}")
    
    try:
        # 构建命令
        # -x 16: 16线程
        # -s 16: 16连接
        # --seed-time=0: BT下载完不保种
        # -d: 目录
        cmd = [
            "aria2c", 
            "-d", download_dir,
            "-x", "16", 
            "-s", "16",
            "--seed-time=0",
            "--summary-interval=0", # 减少日志垃圾
            url
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            # 尝试从 stdout 中解析实际文件名 (可选优化)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ **下载完成**\n\n📂 目录: `{download_dir}`\n📄 文件: `{filename_hint}`\n\n提示: 您现在可以在 [📺 本地视频] 中找到它并推流。",
                parse_mode='Markdown'
            )
        else:
            err_msg = stderr.decode().strip()
            # 截取最后几行错误
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
