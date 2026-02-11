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
    get_main_menu_keyboard,
    get_alist_keyboard, 
    get_settings_keyboard, 
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
        count = len(selected_indices)
        text = "🚀 开始推流 (单图)" if count == 1 else f"🚀 开始轮播 ({count}张)"
        ctrl_row.append(InlineKeyboardButton(text, callback_data="btn_start_slideshow"))
        ctrl_row.append(InlineKeyboardButton("❌ 清空", callback_data="btn_clear_imgs"))
    
    keyboard.append(ctrl_row)
    keyboard.append([InlineKeyboardButton("🔙 返回重选音频", callback_data="btn_audio_stream")])
    return InlineKeyboardMarkup(keyboard)

# --- 启动命令 ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_owner(user_id):
        await update.message.reply_text(
            "👑 **Termux 控制台已就绪**\n请使用底部菜单操作 👇",
            reply_markup=get_main_menu_keyboard(),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("🚫 **未授权访问**")

# --- 回调处理 (Inline Buttons) ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_owner(user_id):
        await query.answer("❌ 无权操作", show_alert=True)
        return

    # 先 answer，防止按钮转圈
    try:
        await query.answer()
    except:
        pass
        
    data = query.data

    # --- 关闭/返回 ---
    if data == "btn_close":
        await query.delete_message()
        return

    # --- 设置菜单 ---
    elif data == "btn_menu_settings":
        config = load_config()
        server = config.get('rtmp_server') or "❌ 未设置"
        keys = config.get('stream_keys', [])
        idx = config.get('active_key_index', 0)
        current_key_name = keys[idx]['name'] if keys and 0 <= idx < len(keys) else "无"

        text = (
            "⚙️ **系统设置中心**\n\n"
            f"📡 **当前服务器**: \n`{server}`\n\n"
            f"🔑 **当前密钥**: `{current_key_name}`\n"
        )
        try:
            await query.edit_message_text(text, reply_markup=get_settings_keyboard(), parse_mode='Markdown')
        except:
            await query.message.reply_text(text, reply_markup=get_settings_keyboard(), parse_mode='Markdown')

    # --- 返回音频列表 ---
    elif data == "btn_audio_stream":
         # 复用音频扫描逻辑，稍微有点 hacky，但能减少代码重复
         # 这里其实应该封装成独立函数，但为了保持逻辑连贯，我们在 callback 里直接处理
         await handle_audio_stream_logic(query, context)

    # --- 链接推流逻辑 (从菜单触发后的返回) ---
    elif data == "btn_start_stream":
        # 这个其实用不到了，因为主菜单直接处理，但这保留作为"返回"的锚点
        pass
    
    # --- 本地视频列表 (点击播放) ---
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

    # --- 音频选定 -> 选择图片 ---
    elif data.startswith("play_aud_"):
        idx = int(data.split("_")[-1])
        audios = context.user_data.get('local_audios', [])
        
        if 0 <= idx < len(audios):
             context.user_data['temp_audio'] = audios[idx]['path']
             context.user_data['temp_audio_name'] = audios[idx]['name']
             
             images = scan_local_images()
             context.user_data['local_images'] = images
             # 初始化为 set 集合
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
        
        # 强制类型转换，防止 user_data 自动序列化为 list
        raw_selected = context.user_data.get('selected_img_indices', set())
        if isinstance(raw_selected, list):
            selected = set(raw_selected)
        else:
            selected = raw_selected
            
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
        try:
            audio_path = context.user_data.get('temp_audio')
            # 同样确保类型安全
            raw_selected = context.user_data.get('selected_img_indices', set())
            selected_indices = set(raw_selected) if isinstance(raw_selected, list) else raw_selected
            images = context.user_data.get('local_images', [])
            
            if not audio_path:
                 await query.answer("❌ 数据丢失，请重试", show_alert=True)
                 return
            if not selected_indices:
                 await query.answer("⚠️ 请至少选择一张图片！", show_alert=True)
                 return
                 
            # 排序保证顺序一致
            selected_image_paths = [images[i]['path'] for i in sorted(list(selected_indices))]
            
            # --- 关键修复 ---
            # 如果只选了一张图，直接传字符串，触发 stream.py 的单图极速优化模式
            # 如果是多张图，传列表，触发轮播模式
            bg_arg = selected_image_paths
            if len(selected_image_paths) == 1:
                bg_arg = selected_image_paths[0]

            await query.edit_message_text("🚀 正在请求推流进程...", parse_mode='Markdown')
            await run_ffmpeg_stream(update, audio_path, background_image=bg_arg)
            
            # 清理状态
            del context.user_data['temp_audio']
            del context.user_data['selected_img_indices']
            
        except Exception as e:
            logger.error(f"启动推流失败: {e}")
            try:
                await query.edit_message_text(f"❌ 启动失败: {e}")
            except:
                pass

    # --- Alist 逻辑 ---
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
        await context.bot.send_message(chat_id=user_id, text=f"🌐 **Alist 访问地址**:\n\n📱 **本机**: `http://127.0.0.1:5244`\n\n📡 **局域网**:\n{ip_list_text}\n\n端口: `5244`", parse_mode='Markdown')
        
    elif data == "btn_alist_admin":
        try:
            res = subprocess.check_output(["alist", "admin"], text=True).strip()
            await context.bot.send_message(chat_id=user_id, text=f"🔐 账号信息:\n`{res}`", parse_mode='Markdown')
        except:
            await context.bot.send_message(chat_id=user_id, text="❌ 获取失败，Alist 是否已安装？")
            
    elif data == "btn_alist_set_pwd":
        context.user_data['state'] = 'waiting_alist_pwd'
        await query.message.reply_text("✍️ **重置 Alist 密码**\n\n请输入新的密码 (回复 `cancel` 取消)：", reply_markup=get_back_keyboard("alist"))

    elif data == "btn_alist_token":
        context.user_data['state'] = 'waiting_alist_token'
        await query.message.reply_text("🔐 **配置 Alist Token**\n\n请输入从 Alist 网页版获取的 Token (回复 `cancel` 取消)：", reply_markup=get_back_keyboard("settings"))
    
    elif data == "btn_alist_fix":
        log_msg, status, new_pid = await fix_alist_config()
        await query.edit_message_text(f"🔧 **修复报告**\n\n{log_msg}\n结果: {status}", reply_markup=get_alist_keyboard(bool(new_pid)), parse_mode='Markdown')
            
    # --- 密钥管理 ---
    elif data == "btn_manage_keys":
        config = load_config()
        keys = config.get('stream_keys', [])
        idx = config.get('active_key_index', 0)
        await query.edit_message_text("🔑 **密钥管理**\n点击列表切换当前使用的密钥：", reply_markup=get_keys_management_keyboard(keys, idx, delete_mode=False), parse_mode='Markdown')

    elif data == "btn_del_key_mode":
        config = load_config()
        keys = config.get('stream_keys', [])
        await query.edit_message_text("🗑️ **删除模式**\n点击下方按钮删除对应的密钥 (不可撤销)：", reply_markup=get_keys_management_keyboard(keys, -1, delete_mode=True), parse_mode='Markdown')

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
            if active_index >= idx and active_index > 0: active_index -= 1
            save_config({'stream_keys': keys, 'active_key_index': active_index})
            await query.edit_message_reply_markup(reply_markup=get_keys_management_keyboard(keys, -1, delete_mode=True))

    elif data == "btn_add_key":
        context.user_data['state'] = 'waiting_key_name'
        await query.message.reply_text("✍️ **新增密钥 - 步骤 1/2**\n\n请输入备注名称 (例如: B站, YouTube)：", reply_markup=get_back_keyboard("manage_keys"))

    elif data == "btn_edit_server":
        context.user_data['state'] = 'waiting_server'
        await query.message.reply_text("✍️ **配置 RTMP 服务器**\n\n请输入完整的 rtmp:// 地址 (回复 `cancel` 取消)：", reply_markup=get_back_keyboard("settings"))
        
    elif data == "btn_view_log":
        log_content = get_log_content()
        if len(log_content) > 3000: log_content = "..." + log_content[-3000:]
        await context.bot.send_message(chat_id=user_id, text=f"📜 **实时日志**:\n\n```\n{log_content}\n```", parse_mode='Markdown')
        
    elif data == "btn_stop_stream_quick":
        if stop_ffmpeg_process():
            await query.message.reply_text("🛑 **已成功停止推流**")
        else:
            await query.answer("⚠️ 当前没有运行中的推流", show_alert=True)


# --- 消息/菜单指令处理 ---
async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id): return
    
    text = update.message.text.strip()
    
    # --- 全局菜单命令匹配 ---
    # 只要匹配到菜单文字，优先执行菜单逻辑，并清除状态
    if text == "🛑 停止推流":
        context.user_data['state'] = None
        if stop_ffmpeg_process():
            await update.message.reply_text("🛑 已停止推流")
        else:
            await update.message.reply_text("⚠️ 当前没有推流任务")
        return

    if text == "📊 状态监控":
        context.user_data['state'] = None
        await update.message.reply_text(get_env_report(), parse_mode='Markdown')
        # 如果正在推流，额外显示日志按钮
        if get_stream_status():
             keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📜 查看实时日志", callback_data="btn_view_log")]])
             await update.message.reply_text("💡 推流正在进行中...", reply_markup=keyboard)
        return

    if text == "♻️ 重启机器人":
        context.user_data['state'] = None
        await update.message.reply_text("♻️ **系统更新/重启中...**\n正在拉取代码并重启，请稍候...", parse_mode='Markdown')
        save_config({'token': TOKEN, 'owner_id': OWNER_ID})
        subprocess.Popen("nohup bash setup.sh > update.log 2>&1 &", shell=True)
        return

    if text == "⚙️ 设置":
        context.user_data['state'] = None
        config = load_config()
        server = config.get('rtmp_server') or "❌ 未设置"
        keys = config.get('stream_keys', [])
        idx = config.get('active_key_index', 0)
        current_key_name = keys[idx]['name'] if keys and 0 <= idx < len(keys) else "无"
        
        info = (
            "⚙️ **系统设置中心**\n\n"
            f"📡 **服务器**: `{server}`\n"
            f"🔑 **当前密钥**: `{current_key_name}`"
        )
        await update.message.reply_text(info, reply_markup=get_settings_keyboard(), parse_mode='Markdown')
        return

    if text == "🗂 Alist":
        context.user_data['state'] = None
        pid = get_alist_pid()
        status_text = "✅ 运行中" if pid else "🔴 已停止"
        await update.message.reply_text(f"🗂 **Alist 网盘管理**\n服务状态: {status_text}", reply_markup=get_alist_keyboard(bool(pid)), parse_mode='Markdown')
        return

    if text == "🔗 链接/Alist":
        context.user_data['state'] = 'waiting_stream_link'
        await update.message.reply_text(
            "🔗 **链接推流模式**\n\n"
            "请直接回复：\n"
            "1. **视频直链** (http/https)\n"
            "2. **Alist 路径** (例如 `/电影/test.mp4`)\n\n"
            "回复 `cancel` 取消。",
            parse_mode='Markdown'
        )
        return

    if text == "📺 本地视频":
        context.user_data['state'] = None
        await update.message.reply_text("🔍 正在扫描本地存储...", parse_mode='Markdown')
        videos = scan_local_videos()
        if not videos:
            await update.message.reply_text("❌ **未找到视频文件**\n请检查 `/sdcard/Download` 目录。", parse_mode='Markdown')
            return
        context.user_data['local_videos'] = videos
        keyboard = []
        for idx, v in enumerate(videos):
            name = v['name']
            if len(name) > 30: name = name[:28] + ".."
            keyboard.append([InlineKeyboardButton(f"🎬 {name} ({format_size(v['size'])})", callback_data=f"play_loc_{idx}")])
        keyboard.append([InlineKeyboardButton("❌ 关闭", callback_data="btn_close")])
        await update.message.reply_text("📂 **本地视频库** (点击播放):", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if text == "🎵 音频+图片":
        context.user_data['state'] = None
        # 调用复用的音频逻辑
        await handle_audio_stream_logic(None, context, update.message)
        return

    # --- 状态机输入处理 ---
    state = context.user_data.get('state')
    if not state: return
    
    # 通用取消
    if text.lower() == 'cancel':
        context.user_data['state'] = None
        await update.message.reply_text("🚫 操作已取消")
        return

    # 1. 链接推流
    if state == 'waiting_stream_link':
        context.user_data['state'] = None
        await run_ffmpeg_stream(update, text)
        
    # 2. Alist 密码
    elif state == 'waiting_alist_pwd':
        try:
            process = subprocess.Popen(["alist", "admin", "set", text], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            await update.message.reply_text(f"✅ **密码已更新**\n`{text}`", parse_mode='Markdown')
        except Exception as e:
             await update.message.reply_text(f"❌ 设置失败: {e}")
        context.user_data['state'] = None
    
    # 3. Alist Token
    elif state == 'waiting_alist_token':
        save_config({'alist_token': text})
        await update.message.reply_text("✅ **Token 已保存**", parse_mode='Markdown')
        context.user_data['state'] = None

    # 4. RTMP Server
    elif state == 'waiting_server':
        if not text.startswith("rtmp"):
            await update.message.reply_text("⚠️ 格式错误，请以 `rtmp://` 开头。")
            return
        save_config({'rtmp_server': text})
        await update.message.reply_text("✅ **服务器地址已更新**", parse_mode='Markdown')
        context.user_data['state'] = None
        
    # 5. 添加密钥 (Key Name)
    elif state == 'waiting_key_name':
        context.user_data['temp_key_name'] = text
        context.user_data['state'] = 'waiting_key_value'
        await update.message.reply_text(f"✍️ **步骤 2/2: 输入密钥**\n名称: `{text}`\n\n请回复 Stream Key：", parse_mode='Markdown')
    
    # 6. 添加密钥 (Key Value)
    elif state == 'waiting_key_value':
        name = context.user_data.get('temp_key_name', '未命名')
        config = load_config()
        keys = config.get('stream_keys', [])
        keys.append({'name': name, 'key': text})
        save_config({'stream_keys': keys, 'active_key_index': len(keys) - 1})
        await update.message.reply_text(f"✅ **密钥已添加**: {name}", parse_mode='Markdown')
        context.user_data['state'] = None


async def handle_audio_stream_logic(query, context, message=None):
    """独立的音频扫描逻辑，供 Callback 和 Text Handler 调用"""
    target = query.message if query else message
    if not target: return
    
    if query: await query.edit_message_text("🔍 正在扫描本地音乐...", parse_mode='Markdown')
    else: await target.reply_text("🔍 正在扫描本地音乐...", parse_mode='Markdown')
    
    audios = scan_local_audio()
    if not audios:
         text = "❌ **未找到音频文件**\n请检查 `/sdcard/Music` 目录。"
         if query: await query.edit_message_text(text, parse_mode='Markdown')
         else: await target.reply_text(text, parse_mode='Markdown')
         return
    
    context.user_data['local_audios'] = audios
    context.user_data['selected_img_indices'] = set()
    
    keyboard = []
    for idx, v in enumerate(audios):
        name = v['name']
        if len(name) > 30: name = name[:28] + ".."
        keyboard.append([InlineKeyboardButton(f"🎵 {name}", callback_data=f"play_aud_{idx}")])
    keyboard.append([InlineKeyboardButton("❌ 关闭", callback_data="btn_close")])
    
    text = "📂 **选择背景音乐**:"
    if query: await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else: await target.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def start_stream_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    if len(context.args) == 0:
        await update.message.reply_text("💡 命令用法: `/stream <链接> [RTMP地址]`", parse_mode='Markdown')
        return
    raw_src = " ".join(context.args).strip()
    await run_ffmpeg_stream(update, raw_src)

async def stop_stream_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    if stop_ffmpeg_process():
        await update.message.reply_text("🛑 已停止推流")
    else:
        await update.message.reply_text("⚠️ 无运行中的任务")

def main():
    print(f"🚀 机器人启动中 (Reply Menu v3.0)...")
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
