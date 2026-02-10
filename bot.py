import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# --- 硬编码配置区域 ---
TOKEN = "7565918204:AAH3E3Bb9Op7Xv-kezL6GISeJj8mA6Ycwug"
OWNER_ID = 1878794912
# --------------------

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """响应 /start 命令"""
    user = update.effective_user
    user_id = user.id
    
    logger.info(f"收到指令: /start 来自 {user.first_name} ({user_id})")
    
    if user_id == OWNER_ID:
        await update.message.reply_text(f"👑 欢迎回来，主人！\n系统正常运行中。\nID: `{user_id}`", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"👋 你好 {user.first_name}！\n我是运行在 Termux 上的测试机器人。\n你的 ID: `{user_id}`", parse_mode='Markdown')

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """回显消息"""
    await update.message.reply_text(f"收到: {update.message.text}")

def main():
    print(f"🚀 正在启动机器人...")
    print(f"👤 管理员 ID: {OWNER_ID}")

    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), echo))
    
    print("✅ 运行成功！按 Ctrl+C 停止。")
    application.run_polling()

if __name__ == '__main__':
    main()
