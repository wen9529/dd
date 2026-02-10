import logging
import asyncio
import subprocess
import os
import signal
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# --- 导入模块 ---
from modules.config import load_config, save_config, is_owner, TOKEN, OWNER_ID, CONFIG_FILE
from modules.utils import get_local_ip, get_all_ips, get_env_report, scan_local_videos, scan_local_audio, scan_local_images, format_size
from modules.alist import get_alist_pid, fix_alist_config
from modules.stream import run_ffmpeg_stream, stop_ffmpeg_process, get_stream_status, get_log_content
from modules.keyboards import get_main_keyboard, get_alist_keyboard, get_stream_settings_keyboard, get_back_keyboard, get_keys_management_keyboard

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# --- 辅助函数：生成图片选择键盘 ---
def get_image_select_keyboard(images, selected_indices):
    keyboard = []
    # 生成图片列表按钮
    for idx, img in enumerate(images):
        is_selected = idx in selected_indices
        mark = "✅" if is_selected else "⬜"
        btn_text = f"{mark} {img['name']}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"toggle_img_{idx}")])
    
    # 底部控制按钮
    ctrl_row = []
    if selected_indices:
        ctrl_row.append(InlineKeyboardButton(f"🚀 开始推流 ({len(selected_indices)}张)", callback_data="btn_start_slideshow"))
        ctrl_row.append(InlineKeyboardButton("❌ 清空", callback_data="btn_clear_imgs"))
    
    keyboard.append(ctrl_row)
    keyboard.append([InlineKeyboardButton("🔙 返回重选音频", callback_data="btn_audio_stream")])
    return InlineKeyboardMarkup(keyboard)

# --- 回调处理 ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_owner(user_id):
        await query.answer("❌ 无权操作", show_alert=True)
        return

    await query.answer()
    data = query.data

    if data == "btn_refresh" or data == "btn_back_main":
        context.user_data['state'] = None
        # 清理临时数据
        if 'temp_audio' in context.user_data: del context.user_data['temp_audio']
        if 'selected_img_indices' in context.user_data: del context.user_data['selected_img_indices']
        
        await query.edit_message_text(
            f"👑 **Termux 控制台**\n当前用户: `{user_id}`\n",
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown'
        )
    elif data == "btn_start_stream":
        context.user_data['state'] = 'waiting_stream_link'
        await query.edit_message_text(
            "🎬 **准备推流 (网络/Alist)**\n\n"
            "请直接回复您要推流的 **视频链接** 或 **Alist 文件路径**。\n"
            "(您可以直接从 Alist 复制链接并发送给我)\n\n"
            "例如：\n"
            "• `http://192.168.1.5:5244/d/电影/test.mp4`\n"
            "• `/电影/test.mp4`\n\n"
            "回复 `cancel` 取消。",
            parse_mode='Markdown'
        )
    
    elif data == "btn_local_stream":
        await query.edit_message_text("🔍 正在扫描本地视频文件...", parse_mode='Markdown')
        videos = scan_local_videos()
        
        if not videos:
            await query.edit_message_text(
                "❌ **未找到视频文件**\n\n"
                "已扫描: `Download`, `Movies`, `DCIM`, `Pictures` 及 Termux 存储。\n\n"
                "💡 **解决办法**:\n"
                "1. 请确认手机中有 `.mp4` 或 `.mkv` 文件。\n"
                "2. 若从未授权，请在 Termux 运行 `termux-setup-storage` 并点击允许。",
                reply_markup=get_back_keyboard(),
                parse_mode='Markdown'
            )
            return

        context.user_data['local_videos'] = videos
        keyboard = []
        for idx, v in enumerate(videos):
            btn_text = f"🎬 {v['name']} ({format_size(v['size'])})"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"play_loc_{idx}")])
        
        keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="btn_back_main")])
        
        await query.edit_message_text(
            "📂 **本地视频列表** (最新的20个):\n点击即可开始推流。",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    # --- 音频推流流程 ---
    elif data == "btn_audio_stream":
        await query.edit_message_text("🔍 正在扫描本地音频文件...", parse_mode='Markdown')
        audios = scan_local_audio()
        
        if not audios:
             await query.edit_message_text(
                "❌ **未找到音频文件**\n\n"
                "已扫描: `Music`, `Download` 及 Termux 存储。\n\n"
                "💡 **解决办法**:\n"
                "1. 请确认手机中有 `.mp3` 或 `.flac` 文件。\n"
                "2. 若从未授权，请在 Termux 运行 `termux-setup-storage` 并点击允许。",
                reply_markup=get_back_keyboard(),
                parse_mode='Markdown'
            )
             return
        
        context.user_data['local_audios'] = audios
        # 清空之前的图片选择
        context.user_data['selected_img_indices'] = set()
        
        keyboard = []
        for idx, v in enumerate(audios):
            btn_text = f"🎵 {v['name']} ({format_size(v['size'])})"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"play_aud_{idx}")])
        
        keyboard.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="btn_back_main")])
        
        await query.edit_message_text(
            "📂 **步骤 1/2: 选择音频文件**\n",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    elif data.startswith("play_aud_"):
        # 选中音频，现在进入图片多选模式
        idx = int(data.split("_")[-1])
        audios = context.user_data.get('local_audios', [])
        
        if 0 <= idx < len(audios):
             context.user_data['temp_audio'] = audios[idx]['path']
             context.user_data['temp_audio_name'] = audios[idx]['name']
             
             # 扫描图片
             images = scan_local_images()
             context.user_data['local_images'] = images
             context.user_data['selected_img_indices'] = set() # 初始化选择集合
             
             if not images:
                 # 无图片，提示用户但允许继续(暂不支持无图模式，这里强制提示)
                 await query.answer("⚠️ 未找到图片 (jpg/png)，请在 Pictures 或 Download 放入图片", show_alert=True)
                 return
             
             await query.edit_message_text(
                f"📂 **步骤 2/2: 选择轮播图片** (支持多选)\n"
                f"已选音频: `{audios[idx]['name']}`\n\n"
                "请点击图片进行勾选，最后点击【开始推流】：",
                reply_markup=get_image_select_keyboard(images, set()),
                parse_mode='Markdown'
             )
        else:
             await query.answer("❌ 文件索引无效", show_alert=True)

    elif data.startswith("toggle_img_"):
        # 切换图片选中状态
        idx = int(data.split("_")[-1])
        selected = context.user_data.get('selected_img_indices', set())
        
        if idx in selected:
            selected.remove(idx)
        else:
            selected.add(idx)
            
        context.user_data['selected_img_indices'] = selected
        
        # 刷新键盘
        images = context.user_data.get('local_images', [])
        await query.edit_message_reply_markup(reply_markup=get_image_select_keyboard(images, selected))

    elif data == "btn_clear_imgs":
        context.user_data['selected_img_indices'] = set()
        images = context.user_data.get('local_images', [])
        await query.edit_message_reply_markup(reply_markup=get_image_select_keyboard(images, set()))

    elif data == "btn_start_slideshow":
        # 开始多图推流
        audio_path = context.user_data.get('temp_audio')
        selected_indices = context.user_data.get('selected_img_indices', set())
        images = context.user_data.get('local_images', [])
        
        if not audio_path:
             await query.answer("❌ 音频路径丢失，请重新操作", show_alert=True)
             return
        
        if not selected_indices:
             await query.answer("⚠️ 请至少选择一张图片", show_alert=True)
             return
             
        # 获取选中的图片路径列表
        selected_image_paths = [images[i]['path'] for i in sorted(list(selected_indices))]
        
        # 开始推流
        await run_ffmpeg_stream(update, audio_path, background_image=selected_image_paths)
        
        # 清理
        del context.user_data['temp_audio']
        del context.user_data['selected_img_indices']


    elif data.startswith("play_loc_"):
        try:
            idx = int(data.split("_")[-1])
            videos = context.user_data.get('local_videos', [])
            if 0 <= idx < len(videos):
                target_video = videos[idx]
                await run_ffmpeg_stream(update, target_video['path'])
            else:
                await query.answer("❌ 文件索引无效，请刷新列表", show_alert=True)
        except Exception as e:
            await query.answer(f"❌ 错误: {e}", show_alert=True)

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

    elif data == "btn_alist_token":
        context.user_data['state'] = 'waiting_alist_token'
        await query.edit_message_text(
            "🔐 **配置 Alist Token**\n\n"
            "为了访问私有文件，请填入 Alist 的 Token。\n"
            "获取方式：Alist 网页版 -> 管理 -> 设置 -> 其他 -> Token\n\n"
            "请直接回复 Token (回复 `cancel` 取消)",
            parse_mode='Markdown'
        )
    
    # --- 修复 Alist 访问 ---
    elif data == "btn_alist_fix":
        log_msg, status, new_pid = await fix_alist_config()
        all_ips = get_all_ips()
        ip_hint = "\n".join([f"`http://{ip.split(': ')[1]}:5244`" for ip in all_ips]) if all_ips else "无法获取 IP"

        await query.edit_message_text(
            f"🔧 **修复结果报告**\n\n{log_msg}\n状态: {status}\n\n📡 **请尝试以下局域网地址**:\n{ip_hint}",
            reply_markup=get_alist_keyboard(bool(new_pid)),
            parse_mode='Markdown'
        )
            
    # --- 推流设置逻辑 ---
    elif data == "btn_stream_settings":
         config = load_config()
         server = config.get('rtmp_server') or "❌ 未设置"
         
         # 获取当前活跃的密钥名称
         keys = config.get('stream_keys', [])
         idx = config.get('active_key_index', 0)
         current_key_name = "无"
         if keys and 0 <= idx < len(keys):
             current_key_name = keys[idx]['name']

         text = (
             "📺 **推流配置面板**\n\n"
             f"🔗 **服务器地址**: \n`{server}`\n\n"
             f"🔑 **当前使用密钥**: \n`{current_key_name}`\n\n"
             "👇 **修改配置**"
         )
         await query.edit_message_text(text, reply_markup=get_stream_settings_keyboard(), parse_mode='Markdown')
    
    # --- 密钥管理 ---
    elif data == "btn_manage_keys":
        config = load_config()
        keys = config.get('stream_keys', [])
        idx = config.get('active_key_index', 0)
        
        text = "🔑 **密钥管理**\n\n请点击下方列表切换当前使用的密钥，或添加/删除。"
        await query.edit_message_text(text, reply_markup=get_keys_management_keyboard(keys, idx, delete_mode=False), parse_mode='Markdown')

    elif data == "btn_del_key_mode":
        config = load_config()
        keys = config.get('stream_keys', [])
        text = "🗑️ **删除模式**\n\n点击下方按钮删除对应的密钥。"
        await query.edit_message_text(text, reply_markup=get_keys_management_keyboard(keys, -1, delete_mode=True), parse_mode='Markdown')

    elif data.startswith("select_key_"):
        idx = int(data.split("_")[-1])
        save_config({'active_key_index': idx})
        
        # 刷新列表显示选中状态
        config = load_config()
        keys = config.get('stream_keys', [])
        await query.edit_message_reply_markup(reply_markup=get_keys_management_keyboard(keys, idx, delete_mode=False))

    elif data.startswith("delete_key_"):
        idx = int(data.split("_")[-1])
        config = load_config()
        keys = config.get('stream_keys', [])
        
        if 0 <= idx < len(keys):
            del keys[idx]
            # 修正 active_index，防止越界
            active_index = config.get('active_key_index', 0)
            if active_index >= idx and active_index > 0:
                active_index -= 1
            
            save_config({'stream_keys': keys, 'active_key_index': active_index})
            
            # 刷新删除列表
            await query.edit_message_reply_markup(reply_markup=get_keys_management_keyboard(keys, -1, delete_mode=True))
        else:
            await query.answer("❌ 删除失败", show_alert=True)

    elif data == "btn_add_key":
        context.user_data['state'] = 'waiting_key_name'
        await query.edit_message_text(
            "✍️ **添加新密钥 - 步骤 1/2**\n\n"
            "请回复一个 **备注名称** (例如: Bilibili, YouTube, 斗鱼)\n\n"
            "(回复 `cancel` 取消)",
            parse_mode='Markdown'
        )

    elif data == "btn_edit_server":
        context.user_data['state'] = 'waiting_server'
        await query.edit_message_text(
            "✍️ **请回复 RTMP 服务器地址**：\n\n例如：`rtmp://live-push.bilivideo.com/live-bvc/`\n\n(回复 `cancel` 取消)",
            parse_mode='Markdown'
        )
    
    # 旧版修改密钥入口（暂时保留，功能重定向或移除，这里在菜单中移除了，保留逻辑防止出错）
    elif data == "btn_edit_key":
         await query.answer("请使用 [🔑 管理推流密钥] 功能", show_alert=True)
        
    elif data == "btn_view_log":
        log_content = get_log_content()
        # 如果日志太长，截断
        if len(log_content) > 3000:
            log_content = "..." + log_content[-3000:]
            
        await context.bot.send_message(
            chat_id=user_id,
            text=f"📜 **实时日志片段**:\n\n```\n{log_content}\n```",
            parse_mode='Markdown'
        )
        
    elif data == "btn_stop_stream_quick":
        if stop_ffmpeg_process():
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
    if not state: return
    
    text = update.message.text.strip()
    
    if text.lower() == 'cancel':
        context.user_data['state'] = None
        await update.message.reply_text("🚫 操作已取消。", reply_markup=get_main_keyboard())
        return

    if state == 'waiting_stream_link':
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
        pid = get_alist_pid()
        await update.message.reply_text("👇 Alist 管理", reply_markup=get_alist_keyboard(bool(pid)))
    
    elif state == 'waiting_alist_token':
        save_config({'alist_token': text})
        await update.message.reply_text(f"✅ **Alist Token 已保存！**\n推流时将自动携带此凭证。", parse_mode='Markdown')
        context.user_data['state'] = None
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
        
    elif state == 'waiting_key_name':
        context.user_data['temp_key_name'] = text
        context.user_data['state'] = 'waiting_key_value'
        await update.message.reply_text(
            f"✍️ **添加新密钥 - 步骤 2/2**\n\n"
            f"名称: `{text}`\n"
            f"请回复该平台的 **推流密钥** (Stream Key)：\n\n"
            "(回复 `cancel` 取消)",
            parse_mode='Markdown'
        )
    
    elif state == 'waiting_key_value':
        name = context.user_data.get('temp_key_name', '未命名')
        key_val = text
        
        config = load_config()
        keys = config.get('stream_keys', [])
        keys.append({'name': name, 'key': key_val})
        
        # 默认选中新添加的
        save_config({'stream_keys': keys, 'active_key_index': len(keys) - 1})
        
        await update.message.reply_text(f"✅ **已添加并选中密钥**: {name}", parse_mode='Markdown')
        context.user_data['state'] = None
        
        # 返回管理界面
        await update.message.reply_text("👇 密钥管理", reply_markup=get_keys_management_keyboard(keys, len(keys)-1))


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

async def start_stream_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    if len(context.args) == 0:
        await update.message.reply_text("💡 **提示**: 建议使用菜单操作。\n\n命令用法: `/stream <链接> [RTMP地址]`", parse_mode='Markdown')
        return

    raw_src = ""
    custom_rtmp = None
    
    if len(context.args) > 1 and "rtmp" in context.args[-1]:
         custom_rtmp = context.args[-1]
         raw_src = " ".join(context.args[:-1]).strip()
    else:
         raw_src = " ".join(context.args).strip()

    await run_ffmpeg_stream(update, raw_src, custom_rtmp)

async def stop_stream_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    if stop_ffmpeg_process():
        await update.message.reply_text("🛑 已停止")
    else:
        await update.message.reply_text("⚠️ 无运行中的推流")

def main():
    print(f"🚀 机器人启动中 (Modular Version)...")
    
    # --- 启动自检逻辑 ---
    print("------------------------------------------")
    if not os.path.exists(CONFIG_FILE):
        print(f"⚠️  警告: 配置文件 {CONFIG_FILE} 未找到。")
        print("   (新手机部署是正常的，请在机器人启动后在设置中重新添加密钥)")
    
    try:
        env_report = get_env_report()
        print(env_report.replace("*", "").replace("`", "")) # 打印纯文本报告到控制台
    except Exception as e:
        print(f"⚠️  环境检查失败: {e}")
    print("------------------------------------------")

    config = load_config()
    final_token = config.get('token')
    
    if final_token == "YOUR_BOT_TOKEN_HERE" or not final_token:
        print("❌ 错误: TOKEN 未配置！请编辑 modules/config.py 或 bot_config.json")
        return

    try:
        application = ApplicationBuilder().token(final_token).build()
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("stream", start_stream_cmd))
        application.add_handler(CommandHandler("stopstream", stop_stream_cmd))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
        application.add_handler(CallbackQueryHandler(button_callback))
        
        print("✅ Polling 开始... (按 Ctrl+C 停止)")
        application.run_polling()
    except Exception as e:
        print(f"❌ 启动崩溃: {e}")
        print("💡 提示: 常见错误如 'NetworkError' 可能是因为缺少 openssl-tool，请运行 'pkg install openssl-tool'")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
