import logging
import asyncio
import subprocess
import os
import signal
import psutil
import sys
import socket
import json
from urllib.parse import quote
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# --- ⚠️ 核心配置区域 ⚠️ ---
# 您执行了 reset，配置可能已丢失。
# 请在此处填入您的 Token 和 ID，或者在 Web 界面/本地编辑器修改。
TOKEN = "7565918204:AAH3E3Bb9Op7Xv-kezL6GISeJj8mA6Ycwug" 
OWNER_ID = 1878794912
# -------------------------

CONFIG_FILE = "bot_config.json"
FFMPEG_LOG_FILE = "ffmpeg.log"
# 全局变量用于存储 FFmpeg 进程
ffmpeg_process = None

# 配置日志 - 输出到标准输出以便 pm2 log 查看
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

def is_owner(user_id):
    """检查用户是否为管理员，并打印调试日志"""
    uid_str = str(user_id).strip()
    owner_str = str(OWNER_ID).strip()
    
    is_match = uid_str == owner_str
    
    if is_match:
        # print(f"✅ [权限通过] 用户 {uid_str} 正在操作")
        pass
    else:
        print(f"❌ [权限拒绝] 用户 {uid_str} 尝试操作，但管理员ID设定为 {owner_str}")
        
    return is_match

# --- 配置管理 ---
def load_config():
    """加载配置文件，如果文件不存在则使用硬编码配置"""
    config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
    
    # 优先使用 Config 文件中的，如果没有则使用全局变量
    return {
        'token': config.get('token', TOKEN),
        'owner_id': config.get('owner_id', OWNER_ID),
        'rtmp': config.get('rtmp', None), # 兼容旧配置
        'rtmp_server': config.get('rtmp_server', ''),
        'stream_key': config.get('stream_key', '')
    }

def save_config(config_update):
    """保存配置文件"""
    try:
        # 读取现有配置以保留其他字段
        current_config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                current_config = json.load(f)
        
        current_config.update(config_update)
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(current_config, f, indent=4)
        logger.info("配置已保存")
    except Exception as e:
        logger.error(f"保存配置失败: {e}")

# --- 辅助功能 ---
def check_program(cmd):
    """检查程序版本"""
    try:
        if cmd == "ffmpeg":
            output = subprocess.check_output(["ffmpeg", "-version"], stderr=subprocess.STDOUT, text=True)
            return output.splitlines()[0].split()[2] 
        elif cmd == "alist":
            output = subprocess.check_output(["alist", "version"], stderr=subprocess.STDOUT, text=True)
            for line in output.splitlines():
                if "Version" in line:
                    return line.split(":")[-1].strip()
            return "Unknown"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

def get_alist_pid():
    """查找 alist 进程 PID"""
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if 'alist' in proc.info['name']:
                return proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None

def get_local_ip():
    """获取本机局域网 IP"""
    try:
        interfaces = psutil.net_if_addrs()
        priority_interfaces = ['wlan0', 'eth0', 'wlan1']
        for iface in priority_interfaces:
            if iface in interfaces:
                for snic in interfaces[iface]:
                    if snic.family == socket.AF_INET:
                        return snic.address
        exclude_prefixes = ('tun', 'ppp', 'lo', 'docker', 'veth', 'rmnet')
        for name, snics in interfaces.items():
            if name.lower().startswith(exclude_prefixes): continue
            for snic in snics:
                if snic.family == socket.AF_INET and not snic.address.startswith("127."):
                    return snic.address
        return "127.0.0.1"
    except Exception:
        return "127.0.0.1"

def get_all_ips():
    """获取所有可能的局域网 IP"""
    ips = []
    try:
        interfaces = psutil.net_if_addrs()
        for name, snics in interfaces.items():
            if name.lower().startswith(('lo', 'tun', 'rmnet')): continue
            for snic in snics:
                if snic.family == socket.AF_INET:
                    ips.append(f"{name}: {snic.address}")
    except:
        pass
    return ips

def get_env_report():
    """生成环境报告文本"""
    ffmpeg_ver = check_program("ffmpeg")
    alist_ver = check_program("alist")
    alist_pid = get_alist_pid()
    ffmpeg_running = ffmpeg_process is not None and ffmpeg_process.poll() is None
    local_ip = get_local_ip()
    
    cpu_usage = psutil.cpu_percent(interval=None)
    mem_info = psutil.virtual_memory()
    mem_usage = f"{mem_info.used / 1024 / 1024:.0f}MB / {mem_info.total / 1024 / 1024:.0f}MB"

    return (
        f"🖥 **服务器环境报告**\n\n"
        f"🌐 **局域网IP**: `{local_ip}`\n\n"
        f"🎥 **FFmpeg**:\n"
        f"• 安装状态: {'✅ ' + ffmpeg_ver if ffmpeg_ver else '❌ 未安装'}\n"
        f"• 推流任务: {'🔴 进行中' if ffmpeg_running else '⚪ 空闲'}\n\n"
        f"🗂 **Alist**:\n"
        f"• 安装状态: {'✅ ' + alist_ver if alist_ver else '❌ 未安装'}\n"
        f"• 运行状态: {'🟢 运行中 (PID ' + str(alist_pid) + ')' if alist_pid else '🔴 已停止'}\n\n"
        f"⚙️ **系统资源**:\n"
        f"• CPU: {cpu_usage}%\n"
        f"• 内存: {mem_usage}"
    )

# --- 核心逻辑 ---
async def run_ffmpeg_stream(update: Update, raw_src: str, custom_rtmp: str = None):
    """执行推流的通用函数"""
    global ffmpeg_process
    
    # 1. 检查是否已有任务
    if ffmpeg_process and ffmpeg_process.poll() is None:
        await update.message.reply_text("⚠️ **推流正在进行中**\n请先使用 `/stopstream` 停止当前任务，或等待其结束。", parse_mode='Markdown')
        return

    # 2. 获取 RTMP 地址
    config = load_config()
    server = config.get('rtmp_server', '')
    key = config.get('stream_key', '')
    legacy_rtmp = config.get('rtmp', '')
    
    rtmp_url = ""
    if custom_rtmp:
        rtmp_url = custom_rtmp
    elif server and key:
        rtmp_url = server + key
    elif legacy_rtmp:
        rtmp_url = legacy_rtmp
        
    if not rtmp_url:
        await update.message.reply_text("❌ **未配置推流地址**\n请先在菜单中点击 [📺 推流设置] 进行配置，或联系管理员。", parse_mode='Markdown')
        return

    # 3. 处理源链接
    # 如果是以 / 开头的路径，默认为 Alist 本地路径，自动添加前缀
    src = raw_src.strip()
    if src.startswith("/"):
        encoded_src = quote(src, safe='/')
        src = f"http://127.0.0.1:5244{encoded_src}"
    # 如果是 http/https 开头的，直接使用
    
    # 4. 发送反馈
    display_rtmp = rtmp_url[:15] + "..." if len(rtmp_url) > 15 else rtmp_url
    await update.message.reply_text(
        f"🚀 **启动推流任务**\n\n"
        f"📄 **源地址**: `{raw_src}`\n"
        f"🔗 **处理后**: `{src}`\n"
        f"📡 **推流目标**: `{display_rtmp}`\n\n"
        "⏳ 正在启动进程...", 
        parse_mode='Markdown'
    )

    # 5. 执行 FFmpeg
    cmd = [
        "ffmpeg", 
        "-re", 
        "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
        "-i", src, 
        "-c:v", "libx264", "-preset", "ultrafast", "-g", "60",
        "-c:a", "aac", "-ar", "44100", "-b:a", "128k", 
        "-f", "flv", 
        rtmp_url
    ]
    
    try:
        # 打开日志文件
        log_file = open(FFMPEG_LOG_FILE, "w")
        
        # 将 stdout 和 stderr 都重定向到日志文件
        ffmpeg_process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
        
        # 等待 3 秒检查进程状态
        await asyncio.sleep(3)
        
        if ffmpeg_process.poll() is not None:
             # 进程已退出，说明启动失败
             log_file.close() # 关闭文件以刷新内容
             
             log_content = "无日志记录"
             try:
                 with open(FFMPEG_LOG_FILE, "r") as f:
                     # 读取最后 800 个字符
                     log_content = f.read()[-800:]
             except Exception as e:
                 log_content = f"读取日志失败: {e}"

             await update.message.reply_text(
                 f"❌ **推流启动失败** (进程意外退出)\n\n"
                 f"🔍 **错误详情 (最后日志)**:\n"
                 f"```\n{log_content}\n```\n"
                 f"请检查源链接是否有效，或 RTMP 地址是否正确。", 
                 parse_mode='Markdown'
             )
             ffmpeg_process = None
        else:
             # 进程仍在运行
             keyboard = InlineKeyboardMarkup([
                 [InlineKeyboardButton("📜 查看实时日志", callback_data="btn_view_log")],
                 [InlineKeyboardButton("🛑 停止推流", callback_data="btn_stop_stream_quick")]
             ])
             await update.message.reply_text(
                 f"✅ **推流已稳定运行**\n"
                 f"PID: {ffmpeg_process.pid}\n\n"
                 f"如果画面仍未显示，请点击下方 [查看实时日志] 排查问题。",
                 reply_markup=keyboard,
                 parse_mode='Markdown'
             )
             
    except Exception as e:
        await update.message.reply_text(f"❌ 启动异常: {e}")

# --- 键盘菜单 ---
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 开始推流", callback_data="btn_start_stream")],
        [InlineKeyboardButton("🗂 Alist 管理", callback_data="btn_alist"), InlineKeyboardButton("📺 推流设置", callback_data="btn_stream_settings")],
        [InlineKeyboardButton("🔍 环境自检", callback_data="btn_env"), InlineKeyboardButton("♻️ 检查更新", callback_data="btn_update")],
        [InlineKeyboardButton("🔄 刷新菜单", callback_data="btn_refresh")]
    ])

def get_alist_keyboard(is_running):
    start_stop_btn = InlineKeyboardButton("🔴 停止服务", callback_data="btn_alist_stop") if is_running else InlineKeyboardButton("🟢 启动服务", callback_data="btn_alist_start")
    return InlineKeyboardMarkup([
        [start_stop_btn],
        [InlineKeyboardButton("ℹ️ 访问地址", callback_data="btn_alist_info"), InlineKeyboardButton("🔑 查看密码", callback_data="btn_alist_admin")],
        [InlineKeyboardButton("📝 重置密码", callback_data="btn_alist_set_pwd"), InlineKeyboardButton("🔧 修复局域网", callback_data="btn_alist_fix")],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="btn_back_main")]
    ])

def get_stream_settings_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 修改推流地址", callback_data="btn_edit_server"), InlineKeyboardButton("🔑 修改推流密钥", callback_data="btn_edit_key")],
        [InlineKeyboardButton("📜 查看推流日志", callback_data="btn_view_log")],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="btn_back_main")]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回主菜单", callback_data="btn_back_main")]])

# --- 回调处理 ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    global ffmpeg_process
    
    if not is_owner(user_id):
        await query.answer("❌ 无权操作", show_alert=True)
        return

    await query.answer()
    data = query.data

    if data == "btn_refresh" or data == "btn_back_main":
        # 清除输入状态
        context.user_data['state'] = None
        await query.edit_message_text(
            f"👑 **Termux 控制台**\n当前用户: `{user_id}`\n",
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown'
        )
    elif data == "btn_start_stream":
        context.user_data['state'] = 'waiting_stream_link'
        await query.edit_message_text(
            "🎬 **准备推流**\n\n"
            "请直接回复您要推流的 **视频链接** 或 **Alist 文件路径**。\n"
            "(您可以直接从 Alist 复制链接并发送给我)\n\n"
            "例如：\n"
            "• `http://192.168.1.5:5244/d/电影/test.mp4`\n"
            "• `/电影/test.mp4`\n\n"
            "回复 `cancel` 取消。",
            parse_mode='Markdown'
        )
    elif data == "btn_env":
        await query.edit_message_text(get_env_report(), reply_markup=get_back_keyboard(), parse_mode='Markdown')
    elif data == "btn_alist":
        pid = get_alist_pid()
        status_text = f"✅ 运行中 (PID: {pid})" if pid else "🔴 已停止"
        await query.edit_message_text(f"🗂 **Alist 面板**\n状态: {status_text}", reply_markup=get_alist_keyboard(bool(pid)), parse_mode='Markdown')
    elif data == "btn_alist_start":
        if not get_alist_pid():
             subprocess.Popen(["alist", "server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
             await asyncio.sleep(2)
        pid = get_alist_pid()
        await query.edit_message_text(f"🗂 **Alist 面板**\n状态: {'✅ 运行中' if pid else '❌ 启动失败'}", reply_markup=get_alist_keyboard(bool(pid)), parse_mode='Markdown')
    elif data == "btn_alist_stop":
        pid = get_alist_pid()
        if pid:
            os.kill(pid, signal.SIGTERM)
            await asyncio.sleep(1)
        pid = get_alist_pid()
        await query.edit_message_text(f"🗂 **Alist 面板**\n状态: {'✅ 运行中' if pid else '🔴 已停止'}", reply_markup=get_alist_keyboard(bool(pid)), parse_mode='Markdown')
    elif data == "btn_alist_info":
        local_ip = get_local_ip()
        all_ips = get_all_ips()
        ip_list_text = "\n".join([f"• `{ip}`" for ip in all_ips]) if all_ips else f"• `{local_ip}`"
        
        await context.bot.send_message(
            chat_id=user_id, 
            text=f"🌐 **Alist 访问地址**:\n\n📱 **本机**: `http://127.0.0.1:5244`\n\n📡 **局域网 (尝试以下地址)**:\n{ip_list_text}\n\n端口: `5244`", 
            parse_mode='Markdown'
        )
    elif data == "btn_alist_admin":
        try:
            res = subprocess.check_output(["alist", "admin"], text=True).strip()
            await context.bot.send_message(chat_id=user_id, text=f"🔐 信息:\n`{res}`", parse_mode='Markdown')
        except:
            await context.bot.send_message(chat_id=user_id, text="❌ 获取失败")
            
    elif data == "btn_alist_set_pwd":
        context.user_data['state'] = 'waiting_alist_pwd'
        await query.edit_message_text(
            "✍️ **请回复新的 Alist 密码**：\n\n(回复 `cancel` 取消)",
            parse_mode='Markdown'
        )
    
    # --- 修复 Alist 访问 ---
    elif data == "btn_alist_fix":
        # 1. 停止 Alist
        pid = get_alist_pid()
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                for _ in range(10): # 等待 5 秒
                    await asyncio.sleep(0.5)
                    if not get_alist_pid():
                        break
                if get_alist_pid():
                    os.kill(pid, signal.SIGKILL)
            except:
                pass
        
        # 2. 查找并修改配置
        fixed_count = 0
        log_msg = "🛠 **执行修复操作...**\n"
        search_paths = [
            os.path.join(os.getcwd(), "data", "config.json"),
            os.path.expanduser("~/.alist/data/config.json"),
        ]
        
        found_config = False
        for p in search_paths:
            if os.path.exists(p):
                found_config = True
                try:
                    with open(p, 'r') as f:
                        config_data = json.load(f)
                    
                    changed = False
                    # 确保 scheme 存在
                    if 'scheme' not in config_data:
                        config_data['scheme'] = {}
                        changed = True
                    
                    # 强制修改 scheme.address
                    if isinstance(config_data['scheme'], dict):
                        if config_data['scheme'].get('address') != '0.0.0.0':
                            config_data['scheme']['address'] = '0.0.0.0'
                            changed = True
                    
                    if changed:
                        with open(p, 'w') as f:
                            json.dump(config_data, f, indent=4)
                        fixed_count += 1
                        log_msg += f"✅ 已修改配置文件: `{p}`\n"
                    else:
                        log_msg += f"👌 配置无需修改: `{p}`\n"
                        
                except Exception as e:
                    log_msg += f"❌ 配置文件错误 `{p}`: {str(e)}\n"
        
        if not found_config:
             log_msg += "⚠️ 未找到配置文件，尝试启动以生成默认配置。\n"

        # 3. 重启 Alist
        subprocess.Popen(["alist", "server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await asyncio.sleep(3)
        
        new_pid = get_alist_pid()
        status = "✅ 重启成功" if new_pid else "❌ 重启失败"
        
        # 获取所有 IP 提示用户
        all_ips = get_all_ips()
        ip_hint = "\n".join([f"`http://{ip.split(': ')[1]}:5244`" for ip in all_ips]) if all_ips else "无法获取 IP"

        await query.edit_message_text(
            f"🔧 **修复结果报告**\n\n{log_msg}\n状态: {status}\n\n📡 **请尝试以下局域网地址**:\n{ip_hint}",
            reply_markup=get_alist_keyboard(bool(new_pid)),
            parse_mode='Markdown'
        )
            
    # --- 新增推流设置逻辑 ---
    elif data == "btn_stream_settings":
         config = load_config()
         server = config.get('rtmp_server') or "❌ 未设置"
         key = config.get('stream_key') or "❌ 未设置"
         
         # 遮挡密钥
         display_key = key
         if key != "❌ 未设置" and len(key) > 8:
             display_key = key[:4] + "****" + key[-4:]

         text = (
             "📺 **推流配置面板**\n\n"
             f"🔗 **服务器地址**: \n`{server}`\n\n"
             f"🔑 **推流密钥**: \n`{display_key}`\n\n"
             "👇 **修改配置**"
         )
         await query.edit_message_text(text, reply_markup=get_stream_settings_keyboard(), parse_mode='Markdown')
         
    elif data == "btn_edit_server":
        context.user_data['state'] = 'waiting_server'
        await query.edit_message_text(
            "✍️ **请回复 RTMP 服务器地址**：\n\n例如：`rtmp://live-push.bilivideo.com/live-bvc/`\n\n(回复 `cancel` 取消)",
            parse_mode='Markdown'
        )
        
    elif data == "btn_edit_key":
        context.user_data['state'] = 'waiting_key'
        await query.edit_message_text(
            "✍️ **请回复 推流密钥**：\n\n例如：`?streamname=...`\n\n(回复 `cancel` 取消)",
            parse_mode='Markdown'
        )
        
    elif data == "btn_view_log":
        log_content = "暂无日志"
        try:
             with open(FFMPEG_LOG_FILE, "r") as f:
                 log_content = f.read()[-1500:] # 获取最后1500字符
        except Exception as e:
             log_content = f"读取失败: {e}"
        
        if not log_content.strip():
            log_content = "日志文件为空，FFmpeg 可能尚未输出任何信息。"

        # 如果日志太长，截断
        if len(log_content) > 3000:
            log_content = "..." + log_content[-3000:]
            
        await context.bot.send_message(
            chat_id=user_id,
            text=f"📜 **实时日志片段**:\n\n```\n{log_content}\n```",
            parse_mode='Markdown'
        )
        
    elif data == "btn_stop_stream_quick":
        if ffmpeg_process:
            ffmpeg_process.terminate()
            ffmpeg_process = None
            await query.edit_message_text("🛑 **已手动停止推流**", reply_markup=get_main_keyboard(), parse_mode='Markdown')
        else:
            await query.edit_message_text("⚠️ **当前没有正在运行的推流**", reply_markup=get_main_keyboard(), parse_mode='Markdown')

    elif data == "btn_update":
         await query.edit_message_text("♻️ **正在更新系统...**\n\n1. 正在备份当前配置...\n2. 拉取最新代码...\n3. 机器人将自动重启。", parse_mode='Markdown')
         save_config({'token': TOKEN, 'owner_id': OWNER_ID})
         subprocess.Popen("nohup bash setup.sh > update.log 2>&1 &", shell=True)

# --- 消息处理（用于接收输入）---
async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id): return
    
    state = context.user_data.get('state')
    if not state: return # 无状态，忽略普通消息
    
    text = update.message.text.strip()
    
    # 取消操作
    if text.lower() == 'cancel':
        context.user_data['state'] = None
        await update.message.reply_text("🚫 操作已取消。", reply_markup=get_main_keyboard())
        return

    if state == 'waiting_stream_link':
        # 清除状态，开始推流
        context.user_data['state'] = None
        await run_ffmpeg_stream(update, text)
        
    elif state == 'waiting_alist_pwd':
        try:
            process = subprocess.Popen(["alist", "admin", "set", text], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()
            
            result_msg = f"✅ **密码已重置**\n\n用户: `admin`\n密码: `{text}`\n\n{stdout}"
            await update.message.reply_text(result_msg, parse_mode='Markdown')
        except Exception as e:
             await update.message.reply_text(f"❌ 设置失败: {e}")
        
        context.user_data['state'] = None
        # 返回 Alist 菜单
        pid = get_alist_pid()
        await update.message.reply_text("👇 Alist 管理", reply_markup=get_alist_keyboard(bool(pid)))

    elif state == 'waiting_server':
        if not text.startswith("rtmp"):
            await update.message.reply_text("⚠️ 地址建议以 `rtmp://` 开头。\n请重新输入，或输入 `cancel` 取消。")
            return
        save_config({'rtmp_server': text})
        await update.message.reply_text(f"✅ **RTMP 服务器地址已更新！**", parse_mode='Markdown')
        context.user_data['state'] = None
        await update.message.reply_text("👇 下一步", reply_markup=get_stream_settings_keyboard())
        
    elif state == 'waiting_key':
        save_config({'stream_key': text})
        await update.message.reply_text(f"✅ **推流密钥已更新！**", parse_mode='Markdown')
        context.user_data['state'] = None
        await update.message.reply_text("👇 配置完成", reply_markup=get_stream_settings_keyboard())


# --- 命令处理 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_owner(user_id):
        await update.message.reply_text(
            f"👑 **Termux 控制台**\n当前用户: `{user_id}`",
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(f"🚫 **未授权**")

async def start_stream(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """通过命令启动推流"""
    if not is_owner(update.effective_user.id): return
    
    if len(context.args) == 0:
        await update.message.reply_text("💡 **提示**: 您现在可以点击菜单中的 [🚀 开始推流] 按钮，然后直接发送链接。\n\n命令用法: `/stream <链接> [RTMP地址]`", parse_mode='Markdown')
        return

    raw_src = ""
    custom_rtmp = None
    
    if len(context.args) > 1 and "rtmp" in context.args[-1]:
         custom_rtmp = context.args[-1]
         raw_src = " ".join(context.args[:-1]).strip()
    else:
         raw_src = " ".join(context.args).strip()

    await run_ffmpeg_stream(update, raw_src, custom_rtmp)

async def stop_stream(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    global ffmpeg_process
    if ffmpeg_process:
        ffmpeg_process.terminate()
        ffmpeg_process = None
        await update.message.reply_text("🛑 已停止")
    else:
        await update.message.reply_text("⚠️ 无运行中的推流")

def main():
    print(f"🚀 机器人启动中...")
    config = load_config()
    final_token = config.get('token')
    
    if final_token == "YOUR_BOT_TOKEN_HERE" or not final_token:
        print("❌ 错误: TOKEN 未配置！请编辑 bot.py 或 bot_config.json")
        return

    application = ApplicationBuilder().token(final_token).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stream", start_stream))
    application.add_handler(CommandHandler("stopstream", stop_stream))
    # 注册消息处理器，用于接收用户输入的配置和链接
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ Polling 开始... (按 Ctrl+C 停止)")
    application.run_polling()

if __name__ == '__main__':
    main()
