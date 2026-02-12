// 移除 GoogleGenAI 引用，改为硬编码测试模式

export const generateBotCode = async (prompt: string, config?: { token?: string, ownerId?: string }): Promise<{ code: string; explanation: string; dependencies: string[] }> => {
  // 模拟网络延迟
  await new Promise(resolve => setTimeout(resolve, 800));
  
  const token = config?.token || "YOUR_BOT_TOKEN_HERE";
  const ownerId = config?.ownerId || "0";

  // 硬编码的 Python 模板
  const code = `import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# --- 配置区域 ---
# 这些变量由 Termux Bot Forge 自动注入
TOKEN = "${token}"
OWNER_ID = ${ownerId}
# ----------------

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if OWNER_ID != 0 and user_id == int(OWNER_ID):
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"欢迎回来，主人！ (ID: {user_id})")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="你好！我是一个运行在 Termux 上的测试机器人。")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """回显用户发送的消息"""
    user_text = update.message.text
    response_text = f"你发送了: {user_text}"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=response_text)

if __name__ == '__main__':
    if TOKEN == "YOUR_BOT_TOKEN_HERE" or not TOKEN:
        print("错误: 未配置 Bot Token。请在代码中填写或在应用设置中配置。")
        exit(1)

    print("启动机器人...")
    application = ApplicationBuilder().token(TOKEN).build()
    
    start_handler = CommandHandler('start', start)
    echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), echo)
    
    application.add_handler(start_handler)
    application.add_handler(echo_handler)
    
    print("机器人正在运行，按 Ctrl+C 停止。")
    application.run_polling()
`;

  return {
    code,
    explanation: "【测试模式】这是一个硬编码的回声机器人（Echo Bot）模板。它会重复你发送的消息，并识别主人 ID。\n\n由于目前 AI 功能已移除，无论你输入什么提示词，都会生成此模板用于测试环境连通性。",
    dependencies: ["python-telegram-bot"]
  };
};

export const askTermuxHelp = async (question: string): Promise<string> => {
  // 模拟延迟
  await new Promise(resolve => setTimeout(resolve, 500));
  
  return `### 测试模式离线助手

目前 AI 功能已禁用。以下是一些常用的 Termux 常用命令供参考：

**1. 更新系统**
\`\`\`bash
pkg update && pkg upgrade
\`\`\`

**2. 安装 Python**
\`\`\`bash
pkg install python
\`\`\`

**3. 访问存储权限**
\`\`\`bash
termux-setup-storage
\`\`\`

如有其他问题，请查阅 [Termux Wiki](https://wiki.termux.com)。`;
};