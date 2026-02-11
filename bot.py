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
from modules.keyboards import (
    get_main_keyboard, 
    get_alist_keyboard, 
    get_settings_keyboard, 
    get_stream_start_keyboard,
    get_back_keyboard, 
    get_keys_management_keyboard
)

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

    # --- 主菜单导航 ---
    if data == "btn_refresh" or data == "btn_back_main":
        context.user_data['state'] = None
        # 清理临时数据
        if 'temp_audio' in context.user_data: del context.user_data['temp_audio']
        if 'selected_img_indices' in context.user_data: del context.user_data['selected_img_indices']
        
        is_streaming = get_stream_status()
        status_text = "🟢 **推流进行中**" if is_streaming else "⚪ **系统空闲**"
        
        await query.edit_message_text(
            f"👑 **Termux 控制台**\n"
            f"当前用户: `{user_id}`\n"
            f"当前状态: {status_text}",
            reply_markup=get_main_keyboard(is_streaming),
            parse_mode='Markdown'
        )
    
    # --- 推流源选择菜单 ---
    elif data == "btn_menu_stream_select":
        if get_stream_status():
            await query.answer("⚠️ 推流正在进行中，请先停止", show_alert=True)
            return
            
        await query.edit_message_text(
            "🎬 **选择推流来源**\n\n"
            "请选择您想要推送的媒体类型：",
            reply_markup=get_stream_start_keyboard(),
            parse_mode='Markdown'
        )

    # --- 设置菜单 ---
    elif data == "btn_menu_settings":
        config = load_config()
        server = config.get('rtmp_server') or "❌ 未设置"
        
        # 获取当前活跃的密钥名称
        keys = config.get('stream_keys', [])
        idx = config.get('active_key_index', 0)
        current_key_name = "无"
        if keys and 0 <= idx < len(keys):
            current_key_name = keys[idx]['name']

        text = (
            "⚙️ **系统设置中心**\n\n"
            f"📡 **当前服务器**: \n`{server}`\n\n"
            f"🔑 **当前密钥**: `{current_key_name}`\n"
        )
        await query.edit_message_text(text, reply_markup=get_settings_keyboard(), parse_mode='Markdown')

    # --- 链接推流逻辑 ---
    elif data == "btn_start_stream":
        context.user_data['state'] = 'waiting_stream_link'
        await query.edit_message_text(
            "🔗 **链接/Alist 推流模式**\n\n"
            "请直接回复：\n"
            "1. **视频直链** (http/https)\n"
            "2. **Alist 路径** (例如 `/电影/avatar.mp4`)\n\n"
            "回复 `cancel` 取消。",
            reply_markup=get_back_keyboard("stream_select"),
            parse_mode='Markdown'
        )
    
    # --- 本地视频列表 ---
    elif data == "btn_local_stream":
        await query.edit_message_text("🔍 正在扫描本地存储...", parse_mode='Markdown')
        videos = scan_local_videos()
        
        if not videos:
            await query.edit_message_text(
                "❌ **未找到视频文件**\n\n"
                "请确保视频在 `/sdcard/Download` 或 `/sdcard/Movies` 目录下。\n"
                "必要时请运行 `termux-setup-storage`。",
                reply_markup=get_back_keyboard("stream_select"),
                parse_mode='Markdown'
            )
            return

        context.user_data['local_videos'] = videos
        keyboard = []
        for idx, v in enumerate(videos):
            # 截断太长的文件名
            name = v['name']
            if len(name) > 30: name = name[:28] + ".."
            btn_text = f"🎬 {name} ({format_size(v['size'])})"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"play_loc_{idx}")])
        
        keyboard.append([InlineKeyboardButton("🔙 返回选择源", callback_data="btn_menu_stream_select")])
        
        await query.edit_message_text(
            "📂 **本地视频库** (最新的30个):\n点击文件名直接开始推流。",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    # --- 本地音频列表 ---
    elif data == "btn_audio_stream":
        await query.edit_message_text("🔍 正在扫描本地音乐...", parse_mode='Markdown')
        audios = scan_local_audio()
        
        if not audios:
             await query.edit_message_text(
                "❌ **未找到音频文件**\n\n"
                "请确保音频在 `/sdcard/Music` 或 `/sdcard/Download` 目录下。",
                reply_markup=get_back_keyboard("stream_select"),
                parse_mode='Markdown'
            )
             return
        
        context.user_data['local_audios'] = audios
        context.user_data['selected_img_indices'] = set()
        
        keyboard = []
        for idx, v in enumerate(audios):
            name = v['name']
            if len(name) > 30: name = name[:28] + ".."
            btn_text = f"🎵 {name} ({format_size(v['size'])})"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"play_aud_{idx}")])
        
        keyboard.append([InlineKeyboardButton("🔙 返回选择源", callback_data="btn_menu_stream_select")])
        
        await query.edit_message_text(
            "📂 **第一步: 选择背景音乐**\n",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    # --- 音频选定 -> 选择图片 ---
    elif data.startswith("play_aud_"):
        idx = int(data.split("_")[-1])
        audios = context.user_data.get('local_audios', [])
        
        if 0 <= idx < len(audios):
             context.user_data['temp_audio'] = audios[idx]['path']
             context.user_data['temp_audio_name'] = audios[idx]['name']
             
             images = scan_local_images()
             context.user_data['local_images'] = images
             context.user_data['selected_img_indices'] = set()
             
             if not images:
                 await query.answer("⚠️ 未找到图片，无法生成视频画面", show_alert=True)
                 return
             
             await query.edit_message_text(
                f"🖼 **第二步: 选择轮播图片** (支持多选)\n"
                f"当前音乐: `{audios[idx]['name']}`\n\n"
                "👇 点击勾选图片，选好后点击【开始推流】",
                reply_markup=get_image_select_keyboard(images, set()),
                parse_mode='Markdown'
             )
        else:
             await query.answer("❌ 文件索引无效", show_alert=True)

    # --- 图片多选逻辑 ---
    elif data.startswith("toggle_img_"):
        idx = int(data.split("_")[-1])
        selected = context.user_data.get('selected_img_indices', set())
        
        if idx in selected:
            selected.remove(idx)
        else:
            selected.add(idx)
            
        context.user_data['selected_img_indices'] = selected
        images = context.user_data.get('local_images', [])
        await query.edit_message_reply_markup(reply_markup=get_image_select_keyboard(images, selected))

    elif data == "btn_clear_imgs":
        context.user_data['selected_img_indices'] = set()
        images = context.user_data.get('local_images', [])
        await query.edit_message_reply_markup(reply_markup=get_image_select_keyboard(images, set()))

    elif data == "btn_start_slideshow":
        audio_path = context.user_data.get('temp_audio')
        selected_indices = context.user_data.get('selected_img_indices', set())
        images = context.user_data.get('local_images', [])
        
        if not audio_path:
             await query.answer("❌ 数据丢失，请重试", show_alert=True)
             return
        if not selected_indices:
             await query.answer("⚠️ 请至少选择一张图片！", show_alert=True)
             return
             
        selected_image_paths = [images[i]['path'] for i in sorted(list(selected_indices))]
        await run_ffmpeg_stream(update, audio_path, background_image=selected_image_paths)
        
        # 清理
        del context.user_data['temp_audio']
        del context.user_data['selected_img_indices']

    # --- 启动本地视频推流 ---
    elif data.startswith("play_loc_"):
        try:
            idx = int(data.split("_")[-1])
            videos = context.user_data.get('local_videos', [])
            if 0 <= idx < len(videos):
                target_video = videos[idx]
                await run_ffmpeg_stream(update, target_video['path'])
            else:
                await query.answer("❌ 文件已不存在", show_alert=True)
        except Exception as e:
            await query.answer(f"❌ 错误: {e}", show_alert=True)

    # --- 状态/环境检查 ---
    elif data == "btn_env":
        await query.edit_message_text(get_env_report(), reply_markup=get_back_keyboard(), parse_mode='Markdown')
        
    # --- Alist 逻辑 ---
    elif data == "btn_alist":
        pid = get_alist_pid()
        status_text = "✅ 运行中" if pid else "🔴 已停止"
        await query.edit_message_text(f"🗂 **Alist 网盘管理**\n服务状态: {status_text}", reply_markup=get_alist_keyboard(bool(pid)), parse_mode='Markdown')
        
    elif data == "btn_alist_start":
        if not get_alist_pid():
             subprocess.Popen(["alist", "server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
             await asyncio.sleep(2)
        pid = get_alist_pid()
        await query.edit_message_reply_markup(reply_markup=get_alist_keyboard(bool(pid)))
        
    elif data == "btn_alist_stop":
        pid = get_alist_pid()
        if pid:
            os.kill(pid, signal.SIGTERM)
            await asyncio.sleep(1)
        pid = get_alist_pid()
        await query.edit_message_reply_markup(reply_markup=get_alist_keyboard(bool(pid)))
        
    elif data == "btn_alist_info":
        local_ip = get_local_ip()
        all_ips = get_all_ips()
        ip_list_text = "\n".join([f"• `{ip}`" for ip in all_ips]) if all_ips else f"• `{local_ip}`"
        
        await context.bot.send_message(
            chat_id=user_id, 
            text=f"🌐 **Alist 访问地址**:\n\n📱 **本机**: `http://127.0.0.1:5244`\n\n📡 **局域网**:\n{ip_list_text}\n\n端口: `5244`", 
            parse_mode='Markdown'
        )
        
    elif data == "btn_alist_admin":
        try:
            res = subprocess.check_output(["alist", "admin"], text=True).strip()
            await context.bot.send_message(chat_id=user_id, text=f"🔐 账号信息:\n`{res}`", parse_mode='Markdown')
        except:
            await context.bot.send_message(chat_id=user_id, text="❌ 获取失败，Alist 是否已安装？")
            
    elif data == "btn_alist_set_pwd":
        context.user_data['state'] = 'waiting_alist_pwd'
        await query.edit_message_text(
            "✍️ **重置 Alist 密码**\n\n请输入新的密码 (回复 `cancel` 取消)：",
            reply_markup=get_back_keyboard("alist"),
            parse_mode='Markdown'
        )

    elif data == "btn_alist_token":
        context.user_data['state'] = 'waiting_alist_token'
        await query.edit_message_text(
            "🔐 **配置 Alist Token**\n\n"
            "请输入从 Alist 网页版获取的 Token (回复 `cancel` 取消)：",
            reply_markup=get_back_keyboard("settings"),
            parse_mode='Markdown'
        )
    
    elif data == "btn_alist_fix":
        log_msg, status, new_pid = await fix_alist_config()
        await query.edit_message_text(
            f"🔧 **修复报告**\n\n{log_msg}\n结果: {status}",
            reply_markup=get_alist_keyboard(bool(new_pid)),
            parse_mode='Markdown'
        )
            
    # --- 密钥管理 ---
    elif data == "btn_manage_keys":
        config = load_config()
        keys = config.get('stream_keys', [])
        idx = config.get('active_key_index', 0)
        await query.edit_message_text(
            "🔑 **密钥管理**\n点击列表切换当前使用的密钥：", 
            reply_markup=get_keys_management_keyboard(keys, idx, delete_mode=False), 
            parse_mode='Markdown'
        )

    elif data == "btn_del_key_mode":
        config = load_config()
        keys = config.get('stream_keys', [])
        await query.edit_message_text(
            "🗑️ **删除模式**\n点击下方按钮删除对应的密钥 (不可撤销)：", 
            reply_markup=get_keys_management_keyboard(keys, -1, delete_mode=True), 
            parse_mode='Markdown'
        )

    elif data.startswith("select_key_"):
        idx = int(data.split("_")[-1])
        save_config({'active_key_index': idx})
        config = load_config()
        keys = config.get('stream_keys', [])
        await query.edit_message_reply_markup(reply_markup=get_keys_management_keyboard(keys, idx, delete_mode=False))

    elif data.startswith("delete_key_"):
        idx = int(data.split("_")[-1])
        config = load_config()
        keys = config.get('stream_keys', [])
        
        if 0 <= idx < len(keys):
            del keys[idx]
            active_index = config.get('active_key_index', 0)
            if active_index >= idx and active_index > 0:
                active_index -= 1
            
            save_config({'stream_keys': keys, 'active_key_index': active_index})
            await query.edit_message_reply_markup(reply_markup=get_keys_management_keyboard(keys, -1, delete_mode=True))
        else:
            await query.answer("❌ 删除失败", show_alert=True)

    elif data == "btn_add_key":
        context.user_data['state'] = 'waiting_key_name'
        await query.edit_message_text(
            "✍️ **新增密钥 - 步骤 1/2**\n\n请输入备注名称 (例如: B站, YouTube)：",
            reply_markup=get_back_keyboard("manage_keys"),
            parse_mode='Markdown'
        )

    elif data == "btn_edit_server":
        context.user_data['state'] = 'waiting_server'
        await query.edit_message_text(
            "✍️ **配置 RTMP 服务器**\n\n请输入完整的 rtmp:// 地址 (回复 `cancel` 取消)：",
            reply_markup=get_back_keyboard("settings"),
            parse_mode='Markdown'
        )
        
    elif data == "btn_view_log":
        log_content = get_log_content()
        if len(log_content) > 3000:
            log_content = "..." + log_content[-3000:]
        await context.bot.send_message(chat_id=user_id, text=f"📜 **实时日志**:\n\n```\n{log_content}\n```", parse_mode='Markdown')
        
    elif data == "btn_stop_stream_quick":
        if stop_ffmpeg_process():
            await query.edit_message_text("🛑 **已成功停止推流**", reply_markup=get_main_keyboard(is_streaming=False), parse_mode='Markdown')
        else:
            await query.answer("⚠️ 当前没有运行中的推流", show_alert=True)
            await query.edit_message_reply_markup(reply_markup=get_main_keyboard(is_streaming=False))

    elif data == "btn_update":
         await query.edit_message_text("♻️ **系统更新中...**\n正在拉取代码并重启，请稍候...", parse_mode='Markdown')
         save_config({'token': TOKEN, 'owner_id': OWNER_ID})
         subprocess.Popen("nohup bash setup.sh > update.log 2>&1 &", shell=True)

# --- 消息处理 ---
async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id): return
    
    state = context.user_data.get('state')
    if not state: return
    
    text = update.message.text.strip()
    
    # 通用取消逻辑
    if text.lower() == 'cancel':
        context.user_data['state'] = None
        await update.message.reply_text("🚫 操作已取消", reply_markup=get_main_keyboard())
        return

    # 1. 链接推流
    if state == 'waiting_stream_link':
        context.user_data['state'] = None
        await run_ffmpeg_stream(update, text)
        
    # 2. Alist 密码
    elif state == 'waiting_alist_pwd':
        try:
            process = subprocess.Popen(["alist", "admin", "set", text], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()
            await update.message.reply_text(f"✅ **密码已更新**\n`{text}`", parse_mode='Markdown')
        except Exception as e:
             await update.message.reply_text(f"❌ 设置失败: {e}")
        context.user_data['state'] = None
        pid = get_alist_pid()
        await update.message.reply_text("🗂 返回 Alist 面板", reply_markup=get_alist_keyboard(bool(pid)))
    
    # 3. Alist Token
    elif state == 'waiting_alist_token':
        save_config({'alist_token': text})
        await update.message.reply_text("✅ **Token 已保存**", parse_mode='Markdown')
        context.user_data['state'] = None
        await update.message.reply_text("⚙️ 返回设置中心", reply_markup=get_settings_keyboard())

    # 4. RTMP Server
    elif state == 'waiting_server':
        if not text.startswith("rtmp"):
            await update.message.reply_text("⚠️ 格式错误，请以 `rtmp://` 开头。")
            return
        save_config({'rtmp_server': text})
        await update.message.reply_text("✅ **服务器地址已更新**", parse_mode='Markdown')
        context.user_data['state'] = None
        await update.message.reply_text("⚙️ 返回设置中心", reply_markup=get_settings_keyboard())
        
    # 5. 添加密钥 (Key Name)
    elif state == 'waiting_key_name':
        context.user_data['temp_key_name'] = text
        context.user_data['state'] = 'waiting_key_value'
        await update.message.reply_text(
            f"✍️ **步骤 2/2: 输入密钥**\n名称: `{text}`\n\n请回复 Stream Key：",
            parse_mode='Markdown'
        )
    
    # 6. 添加密钥 (Key Value)
    elif state == 'waiting_key_value':
        name = context.user_data.get('temp_key_name', '未命名')
        config = load_config()
        keys = config.get('stream_keys', [])
        keys.append({'name': name, 'key': text})
        
        save_config({'stream_keys': keys, 'active_key_index': len(keys) - 1})
        
        await update.message.reply_text(f"✅ **密钥已添加**: {name}", parse_mode='Markdown')
        context.user_data['state'] = None
        await update.message.reply_text("🔑 返回密钥管理", reply_markup=get_keys_management_keyboard(keys, len(keys)-1))


# --- 命令处理 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_owner(user_id):
        is_streaming = get_stream_status()
        status_text = "🟢 **推流进行中**" if is_streaming else "⚪ **系统空闲**"
        
        await update.message.reply_text(
            f"👑 **Termux 控制台**\n"
            f"当前用户: `{user_id}`\n"
            f"当前状态: {status_text}",
            reply_markup=get_main_keyboard(is_streaming),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("🚫 **未授权访问**")

async def start_stream_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    if len(context.args) == 0:
        await update.message.reply_text("💡 命令用法: `/stream <链接> [RTMP地址]`\n或使用菜单操作。", parse_mode='Markdown')
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
        await update.message.reply_text("🛑 已停止推流")
    else:
        await update.message.reply_text("⚠️ 无运行中的任务")

def main():
    print(f"🚀 机器人启动中 (App Menu v2.0)...")
    if not os.path.exists(CONFIG_FILE):
        print(f"⚠️  配置文件 {CONFIG_FILE} 不存在，将在首次运行时创建。")
    
    config = load_config()
    final_token = config.get('token')
    
    if final_token == "YOUR_BOT_TOKEN_HERE" or not final_token:
        print("❌ 错误: TOKEN 未配置！")
        return

    try:
        application = ApplicationBuilder().token(final_token).build()
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("stream", start_stream_cmd))
        application.add_handler(CommandHandler("stopstream", stop_stream_cmd))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
        application.add_handler(CallbackQueryHandler(button_callback))
        
        print("✅ 服务已就绪，按 Ctrl+C 停止")
        application.run_polling()
    except Exception as e:
        print(f"❌ 启动失败: {e}")

if __name__ == '__main__':
    main()
