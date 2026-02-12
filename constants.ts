
import { StreamConfig } from "./types";

export const DEFAULT_STREAM_CONFIG: StreamConfig = {
  githubUser: "your-username",
  githubRepo: "stream-repo",
  githubPat: "",
  telegramBotToken: "",
  telegramAdminId: "",
  telegramRtmpUrl: "rtmp://x.rtmp.t.me/s/",
  telegramStreamKey: "",
  alistPassword: "admin",
  aria2Secret: "streamforge",
  fileName: "movie.mp4",
  fileUrl: "",
  defaultCoverUrl: "https://images.unsplash.com/photo-1614850523459-c2f4c699c52e?q=80&w=1920&auto=format&fit=crop",
  videoBitrate: "6000k",
};

export const SYSTEM_INSTRUCTION = "You are a technical assistant for StreamForge. You help users configure their streaming setup involving Alist, Termux, and GitHub Actions. You can provide FFmpeg command fixes, debug bot scripts, and explain configuration options. Be concise and technical.";

export const GENERATE_ENV_CONTENT = (config: StreamConfig) => `TG_BOT_TOKEN=${config.telegramBotToken}
TG_ADMIN_ID=${config.telegramAdminId}
GITHUB_OWNER=${config.githubUser}
GITHUB_REPO=${config.githubRepo}
GITHUB_PAT=${config.githubPat}
RTMP_URL=${config.telegramRtmpUrl}${config.telegramStreamKey}
DEFAULT_COVER=${config.defaultCoverUrl}
ALIST_HOST=http://127.0.0.1:5244
ALIST_USER=admin
ALIST_PASSWORD=${config.alistPassword}`;

export const PYTHON_BOT_SCRIPT = `import os
import logging
import requests
import mimetypes
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# Load .env from User Home Directory (Termux Root)
home_dir = os.path.expanduser("~")
env_path = os.path.join(home_dir, ".env")
load_dotenv(env_path)

BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
ADMIN_ID = os.getenv("TG_ADMIN_ID")
GITHUB_OWNER = os.getenv("GITHUB_OWNER")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_PAT = os.getenv("GITHUB_PAT")
RTMP_URL = os.getenv("RTMP_URL")
DEFAULT_COVER = os.getenv("DEFAULT_COVER", "https://images.unsplash.com/photo-1614850523459-c2f4c699c52e?q=80&w=1920&auto=format&fit=crop")

ALIST_HOST = os.getenv("ALIST_HOST", "http://127.0.0.1:5244")
ALIST_USER = os.getenv("ALIST_USER", "admin")
ALIST_PASSWORD = os.getenv("ALIST_PASSWORD", "admin")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

alist_token = None

# --- Helpers ---
def get_alist_token():
    global alist_token
    try:
        res = requests.post(f"\${ALIST_HOST}/api/auth/login", json={"username": ALIST_USER, "password": ALIST_PASSWORD})
        if res.status_code == 200:
            data = res.json()
            if data.get('code') == 200:
                alist_token = data['data']['token']
                return alist_token
    except Exception as e: logger.error(f"Login Error: \${e}")
    return None

def alist_req(endpoint, data=None):
    token = alist_token or get_alist_token()
    headers = {"Authorization": token, "Content-Type": "application/json"}
    try:
        url = f"\${ALIST_HOST}\${endpoint}"
        res = requests.post(url, json=data, headers=headers)
        if res.json().get('code') == 401:
            headers["Authorization"] = get_alist_token()
            res = requests.post(url, json=data, headers=headers)
        return res.json()
    except: return {}

def github_api(method, endpoint, json_data=None):
    headers = {
        "Authorization": f"Bearer \${GITHUB_PAT}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    url = f"https://api.github.com/repos/\${GITHUB_OWNER}/\${GITHUB_REPO}/\${endpoint}"
    if method == "POST": return requests.post(url, json=json_data, headers=headers)
    if method == "GET": return requests.get(url, headers=headers)
    return None

def is_audio_file(filename):
    mime, _ = mimetypes.guess_type(filename)
    if mime and mime.startswith('audio'): return True
    # Fallback for common extensions if mime is None
    ext = filename.lower().split('.')[-1]
    return ext in ['mp3', 'flac', 'wav', 'm4a', 'aac', 'ogg']

# --- Handlers ---
async def start(update: Update, context):
    if str(update.effective_user.id) != str(ADMIN_ID): return
    kb = [["📂 浏览文件", "🛑 停止推流"], ["ℹ️ 帮助", "⚙️ 状态"]]
    await update.message.reply_text("👋 *StreamForge Ultimate*", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True), parse_mode='Markdown')

async def menu_handler(update: Update, context):
    if str(update.effective_user.id) != str(ADMIN_ID): return
    msg = update.message.text.strip()
    
    if msg == "📂 浏览文件": await show_dir(update, "/", 1)
    elif msg == "🛑 停止推流": await stop_stream(update)
    elif msg == "⚙️ 状态": await update.message.reply_text(f"Bot运行中\\nAlist: {'✅' if alist_token else '❌'}")
    elif msg == "ℹ️ 帮助": await update.message.reply_text("支持视频直推及音频+封面自动合成推流。")
    elif msg.startswith("http"): 
        await update.message.reply_text(f"🔗 检测到链接，准备推流...")
        await trigger_stream(update, msg, "Direct Link")

async def show_dir(obj, path, page):
    data = alist_req("/api/fs/list", {"path": path, "page": page, "per_page": 10})
    content = data.get('data', {}).get('content', [])
    total = data.get('data', {}).get('total', 0)
    content.sort(key=lambda x: x['is_dir'], reverse=True)
    
    kb = []
    if path != "/":
        parent = os.path.dirname(path.rstrip('/')) or "/"
        kb.append([InlineKeyboardButton("🔙 返回上级", callback_data=f"nav|\${parent}|1")])
    
    for f in content:
        name = f['name']
        fp = f"\${path.rstrip('/')}/\${name}"
        icon = "📁" if f['is_dir'] else ("🎵" if is_audio_file(name) else "🎬")
        
        if f['is_dir']: kb.append([InlineKeyboardButton(f"\${icon} \${name}", callback_data=f"nav|\${fp}|1")])
        else: kb.append([InlineKeyboardButton(f"\${icon} \${name}", callback_data=f"play|\${fp}")])

    nav_row = []
    if page > 1: nav_row.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"nav|\${path}|\${page-1}"))
    if page * 10 < total: nav_row.append(InlineKeyboardButton("下一页 ➡️", callback_data=f"nav|\${path}|\${page+1}"))
    if nav_row: kb.append(nav_row)

    markup = InlineKeyboardMarkup(kb)
    txt = f"📂 路径: \`\${path}\`\\n📄 页码: \${page}"
    if isinstance(obj, Update): await obj.message.reply_text(txt, reply_markup=markup, parse_mode='Markdown')
    else: await obj.callback_query.edit_message_text(txt, reply_markup=markup, parse_mode='Markdown')

async def trigger_stream(obj, url, name):
    target = obj.message if isinstance(obj, Update) else obj.callback_query
    
    inputs = {"file_url": url, "rtmp_url": RTMP_URL}
    mode_text = "🎬 视频模式"
    
    # Auto-detect audio mode
    if is_audio_file(name):
        mode_text = "🎵 音频+封面模式"
        inputs["image_url"] = DEFAULT_COVER # Use default cover, or extend logic to ask user
        
    status_msg = await target.reply_text(f"🚀 启动 GitHub Actions...\\n\${mode_text}\\n📄 内容: \${name}")
    
    res = github_api("POST", "actions/workflows/stream.yml/dispatches", {
        "ref": "main",
        "inputs": inputs
    })
    
    if res.status_code == 204:
        await status_msg.edit_text(f"✅ 推流任务已提交! (\${mode_text})\\n📺 请关注直播间。")
    else:
        await status_msg.edit_text(f"❌ 启动失败: \${res.status_code}\\n\${res.text}")

async def stop_stream(update):
    msg = await update.message.reply_text("🔍 正在查找运行中的任务...")
    runs = github_api("GET", "actions/runs?status=in_progress").json()
    count = 0
    if 'workflow_runs' in runs:
        for run in runs['workflow_runs']:
            if run['name'] == 'Alist Stream to Telegram':
                github_api("POST", f"actions/runs/\${run['id']}/cancel")
                count += 1
    await msg.edit_text(f"🛑 已发送取消指令给 \${count} 个任务。")

async def cb_handler(update: Update, context):
    q = update.callback_query
    await q.answer()
    parts = q.data.split("|")
    action = parts[0]
    
    if action == "nav": await show_dir(update, parts[1], int(parts[2]))
    elif action == "play":
        path = parts[1]
        res = alist_req("/api/fs/get", {"path": path})
        raw = res.get('data', {}).get('raw_url')
        if raw: await trigger_stream(update, raw, os.path.basename(path))
        else: await q.edit_message_text("❌ 无法获取直链")

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))
    app.add_handler(CallbackQueryHandler(cb_handler))
    logger.info(f"Bot Started... Token: {'*' * 5}{BOT_TOKEN[-5:] if BOT_TOKEN else 'None'}")
    app.run_polling()
`;

export const TERMUX_SETUP_SCRIPT = (config: StreamConfig) => `#!/bin/bash
# StreamForge Ultimate Setup Script

echo "🚀 Starting Setup..."

# 0. Safety Check for .env file in HOME Directory
ENV_FILE="\$HOME/.env"

if [ -f "\$ENV_FILE" ]; then
  echo "⚠️  Found existing .env file at \$ENV_FILE"
  echo "    Skipping configuration generation to protect your secrets."
  echo "    To overwrite, run: rm \$ENV_FILE"
else
  echo "⚙️  Configuring Environment Variables in \$ENV_FILE..."
  cat << EOF > "\$ENV_FILE"
${GENERATE_ENV_CONTENT(config)}
EOF
fi

# 1. Update and Install System Packages
echo "📦 Installing System Packages..."
pkg update -y
pkg install -y python alist aria2 nodejs git ffmpeg

# 2. Install Node.js Global Packages
echo "📦 Installing PM2..."
npm install -g pm2

# 3. Install Python Dependencies
echo "📦 Installing Python Libs..."
pip install python-telegram-bot requests python-dotenv

# Generate Aria2 Secret if empty
ARIA_RPC=${config.aria2Secret}

echo "📥 Configuring Aria2 for Alist..."
mkdir -p ~/.config/aria2
cat << EOF > ~/.config/aria2/aria2.conf
enable-rpc=true
rpc-allow-origin-all=true
rpc-listen-all=true
rpc-secret=$ARIA_RPC
EOF

echo "📄 Creating Intelligent Bot..."
cat << 'PYTHON_EOF' > bot.py
${PYTHON_BOT_SCRIPT}
PYTHON_EOF

echo "✅ Starting Services..."
# Start Aria2 in background
pm2 start aria2c --name aria2 -- --conf-path=\$HOME/.config/aria2/aria2.conf -D
# Start Alist
pm2 start alist --name alist -- server
# Start Bot
pm2 start bot.py --name stream-bot --interpreter python

pm2 save
echo "🎉 Done! Alist Aria2 Secret: $ARIA_RPC"
echo "ℹ️  Bot Token & Config saved to: \$ENV_FILE"
`;

export const GITHUB_WORKFLOW_TEMPLATE = (config: StreamConfig) => `name: Alist Stream to Telegram

on:
  workflow_dispatch:
    inputs:
      file_url:
        description: 'Media URL (Video or Audio)'
        required: true
      image_url:
        description: 'Cover Image URL (For Audio Mode)'
        required: false
      rtmp_url:
        description: 'RTMP URL'
        required: true

jobs:
  stream:
    runs-on: ubuntu-latest
    timeout-minutes: 360 # 6 Hours Max
    steps:
      - uses: actions/checkout@v3
      - name: Install FFmpeg
        run: sudo apt-get update && sudo apt-get install -y ffmpeg
      
      - name: Stream to Telegram
        run: |
          FILE_URL="\${{ github.event.inputs.file_url }}"
          IMAGE_URL="\${{ github.event.inputs.image_url }}"
          RTMP_URL="\${{ github.event.inputs.rtmp_url }}"
          
          # High Quality Audio Settings: AAC 320k 48kHz
          # High Quality Video Settings: ${config.videoBitrate} bitrate, Medium Preset, 1080p
          
          if [ -n "$IMAGE_URL" ]; then
            echo "🎵 Audio + Image Mode Detected"
            echo "Audio: $FILE_URL"
            echo "Image: $IMAGE_URL"
            
            # -loop 1: Loop the image
            # -framerate 30: Create 30fps video
            # -shortest: End stream when audio ends
            # -tune stillimage: Optimize encoding for static image
            
            ffmpeg -re \
              -loop 1 -framerate 30 -i "$IMAGE_URL" \
              -i "$FILE_URL" \
              -c:v libx264 -preset medium -tune stillimage -b:v 4000k -maxrate 4000k -bufsize 8000k \
              -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p" \
              -c:a aac -b:a 320k -ar 48000 -ac 2 \
              -shortest \
              -f flv "$RTMP_URL"
              
          else
            echo "🎬 Video Mode Detected"
            echo "Video: $FILE_URL"
            
            # -reconnect flags: Robustness against network drops
            # -preset medium: Better quality than veryfast
            # -profile:v high: High profile for better quality
            
            ffmpeg -re \
              -reconnect 1 -reconnect_at_eof 1 -reconnect_streamed 1 -reconnect_delay_max 5 \
              -i "$FILE_URL" \
              -c:v libx264 -preset medium -profile:v high -level 4.1 \
              -b:v ${config.videoBitrate} -maxrate ${config.videoBitrate} -bufsize 12000k \
              -vf "scale=1920:-2:flags=lanczos" \
              -pix_fmt yuv420p -g 60 \
              -c:a aac -b:a 320k -ar 48000 -ac 2 \
              -f flv "$RTMP_URL"
          fi
`;
