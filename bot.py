import logging
import asyncio
import subprocess
import os
import signal
import sys
from urllib.parse import quote
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# --- 导入模块 ---
from modules.config import load_config, save_config, is_owner, TOKEN, OWNER_ID, CONFIG_FILE
from modules.utils import get_local_ip, get_all_ips, get_env_report, scan_local_audio, scan_local_images, format_size
from modules.alist import get_alist_pid, fix_alist_config, alist_list_files
from modules.cloudflared import get_cloudflared_pid, start_cloudflared, stop_cloudflared
from modules.stream import run_ffmpeg_stream, stop_ffmpeg_process, get_stream_status, get_log_content
from modules.downloader import aria2_download_task
from modules.keyboards import (
    get_main_menu_keyboard,
    get_alist_keyboard, 
    get_settings_keyboard, 
    get_back_keyboard, 
    get_keys_management_keyboard,
    get_alist_browser_keyboard,
    get_alist_file_actions_keyboard
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

# --- Alist 浏览逻辑核心 ---
async def update_alist_browser(query, context, path):
    """刷新文件浏览消息"""
    success, items = alist_list_files(path)
    
    if not success:
        await query.answer(f"❌ 读取失败: {items}", show_alert=True)
        return

    # 保存当前状态到 context
    context.user_data['alist_path'] = path
    context.user_data['alist_items'] = items # 缓存当前目录文件列表，以便通过索引查找
    
    # 排序并生成键盘
    keyboard = get_alist_browser_keyboard(path, items)
    
    try:
        await query.edit_message_text(
            f"☁️ **云盘浏览**\n📂 路径: `{path}`",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    except Exception:
        # 消息未变动时忽略错误
        pass

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

    # --- 1. Alist 浏览器导航 ---
    elif data.startswith("alist_go:"):
        try:
            idx = int(data.split(":")[1])
            items = context.user_data.get('alist_items', [])
            current_path = context.user_data.get('alist_path', "/")
            
            if 0 <= idx < len(items):
                target = items[idx]
                if target['is_dir']:
                    # 进入目录
                    new_path = os.path.join(current_path, target['name']).replace("\\", "/")
                    await update_alist_browser(query, context, new_path)
                else:
                    # 选中文件
                    context.user_data['alist_selected_file'] = target
                    context.user_data['alist_selected_path'] = os.path.join(current_path, target['name']).replace("\\", "/")
                    
                    size_str = format_size(target['size'])
                    text = (
                        f"📄 **文件操作**\n\n"
                        f"文件名: `{target['name']}`\n"
                        f"大小: {size_str}\n\n"
                        "请选择操作："
                    )
                    await query.edit_message_text(text, reply_markup=get_alist_file_actions_keyboard(), parse_mode='Markdown')
            else:
                await query.answer("❌ 列表已过期，请刷新", show_alert=True)
        except Exception as e:
            logger.error(f"Browser error: {e}")
            await query.answer("❌ 导航错误", show_alert=True)

    elif data == "alist_up":
        current_path = context.user_data.get('alist_path', "/")
        if current_path != "/":
            parent_path = os.path.dirname(current_path.rstrip("/"))
            if not parent_path: parent_path = "/"
            await update_alist_browser(query, context, parent_path)
        else:
            await query.answer("已经是根目录了", show_alert=True)

    elif data == "alist_act_back":
        # 返回当前目录列表
        path = context.user_data.get('alist_path', "/")
        await update_alist_browser(query, context, path)

    elif data == "alist_act_stream":
        # Alist 推流
        file_path = context.user_data.get('alist_selected_path')
        if not file_path:
            await query.answer("❌ 文件信息丢失", show_alert=True)
            return
        
        encoded_path = quote(file_path, safe='/')
        
        await query.edit_message_text("🚀 正在请求推流进程...", parse_mode='Markdown')
        await run_ffmpeg_stream(update, file_path) 

    elif data == "alist_act_download":
        # Alist 下载
        file_path = context.user_data.get('alist_selected_path')
        if not file_path: return
        encoded_path = quote(file_path, safe='/')
        full_url = f"http://127.0.0.1:5244/d{encoded_path}"
        
        await query.edit_message_text("🚀 已添加到后台下载队列", parse_mode='Markdown')
        asyncio.create_task(aria2_download_task(full_url, context, user_id))

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
         await handle_audio_stream_logic(query, context)

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

    # --- Alist & Tunnel 逻辑 ---
    elif data == "btn_alist_start":
        if not get_alist_pid():
             subprocess.Popen(["alist", "server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
             await asyncio.sleep(2)
        pid = get_alist_pid()
        cft_pid = get_cloudflared_pid()
        await query.edit_message_reply_markup(reply_markup=get_alist_keyboard(bool(pid), bool(cft_pid)))
        
    elif data == "btn_alist_stop":
        pid = get_alist_pid()
        if pid:
            os.kill(pid, signal.SIGTERM)
            await asyncio.sleep(1)
        pid = get_alist_pid()
        cft_pid = get_cloudflared_pid()
        await query.edit_message_reply_markup(reply_markup=get_alist_keyboard(bool(pid), bool(cft_pid)))

    # Cloudflare Tunnel 控制
    elif data == "btn_cft_token":
        context.user_data['state'] = 'waiting_cft_token'
        await query.message.reply_text(
            "🚇 **配置 Cloudflare Tunnel**\n\n"
            "请输入您的 Tunnel Token (通常以 `eyJh` 开头)。\n"
            "您可以在 Cloudflare Zero Trust 面板创建 Tunnel 获取。\n\n"
            "回复 `cancel` 取消。", 
            reply_markup=get_back_keyboard("main")
        )
    
    elif data == "btn_cft_toggle":
        pid = get_cloudflared_pid()
        if pid:
            success, msg = stop_cloudflared()
            await query.answer(f"🛑 {msg}")
        else:
            success, msg = start_cloudflared()
            if not success:
                await query.answer(f"❌ 启动失败: {msg}", show_alert=True)
            else:
                await query.answer("🚀 正在启动...", show_alert=False)
                
        await asyncio.sleep(2)
        # 刷新状态
        alist_pid = get_alist_pid()
        cft_pid = get_cloudflared_pid()
        await query.edit_message_reply_markup(reply_markup=get_alist_keyboard(bool(alist_pid), bool(cft_pid)))
        
    elif data == "btn_alist_info":
        local_ip = get_local_ip()
        all_ips = get_all_ips()
        ip_list_text = "\n".join([f"• `{ip}`" for ip in all_ips]) if all_ips else f"• `{local_ip}`"
        
        cft_pid = get_cloudflared_pid()
        tunnel_status = "🟢 运行中" if cft_pid else "⚪ 未运行"
        
        await context.bot.send_message(
            chat_id=user_id, 
            text=f"🌐 **Alist 访问地址**:\n\n📱 **本机**: `http://127.0.0.1:5244`\n\n📡 **局域网**:\n{ip_list_text}\n\n🚇 **内网穿透**: {tunnel_status}\n(请在 CF 面板查看公网域名)", 
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
        await query.message.reply_text("✍️ **重置 Alist 密码**\n\n请输入新的密码 (回复 `cancel` 取消)：", reply_markup=get_back_keyboard("alist"))

    elif data == "btn_alist_token":
        context.user_data['state'] = 'waiting_alist_token'
        await query.message.reply_text("🔐 **配置 Alist Token**\n\n请输入从 Alist 网页版获取的 Token (回复 `cancel` 取消)：", reply_markup=get_back_keyboard("settings"))
    
    elif data == "btn_alist_fix":
        log_msg, status, new_pid = await fix_alist_config()
        cft_pid = get_cloudflared_pid()
        await query.edit_message_text(f"🔧 **修复报告**\n\n{log_msg}\n结果: {status}", reply_markup=get_alist_keyboard(bool(new_pid), bool(cft_pid)), parse_mode='Markdown')
            
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
        cft_pid = get_cloudflared_pid()
        status_text = "✅ 运行中" if pid else "🔴 已停止"
        await update.message.reply_text(f"🗂 **Alist 网盘管理**\n服务状态: {status_text}", reply_markup=get_alist_keyboard(bool(pid), bool(cft_pid)), parse_mode='Markdown')
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
    
    if text == "📥 离线下载":
        context.user_data['state'] = 'waiting_download_link'
        await update.message.reply_text(
            "📥 **离线下载 (Aria2)**\n\n"
            "请回复下载链接 (支持 HTTP/HTTPS/磁力链接)。\n"
            "文件将保存到 `/sdcard/Download`。\n\n"
            "回复 `cancel` 取消。",
            parse_mode='Markdown'
        )
        return

    # --- 新增：云盘浏览逻辑 (替代原本地视频) ---
    if text == "☁️ 云盘浏览" or text == "📺 本地视频":
        context.user_data['state'] = None
        
        # 检查 Alist 是否存活
        if not get_alist_pid():
            await update.message.reply_text("⚠️ **Alist 未启动**\n无法浏览文件，请先启动 Alist。", reply_markup=get_alist_keyboard(False, False), parse_mode='Markdown')
            return

        await update.message.reply_text("🔍 正在连接 Alist...", parse_mode='Markdown')
        
        # 获取根目录
        success, items = alist_list_files("/")
        if not success:
            await update.message.reply_text(f"❌ **连接失败**\n请检查 Alist Token 是否配置正确。\n错误: `{items}`", parse_mode='Markdown')
            return
            
        context.user_data['alist_path'] = "/"
        context.user_data['alist_items'] = items
        
        keyboard = get_alist_browser_keyboard("/", items)
        await update.message.reply_text("☁️ **云盘浏览**\n📂 路径: `/`", reply_markup=keyboard, parse_mode='Markdown')
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

    # 7. 离线下载
    elif state == 'waiting_download_link':
        context.user_data['state'] = None
        if not (text.startswith("http") or text.startswith("magnet")):
             await update.message.reply_text("⚠️ 链接格式错误，仅支持 HTTP/HTTPS/Magnet")
             return
        
        await update.message.reply_text("🚀 **任务已添加后台**\n正在使用 Aria2 下载，完成后会通知您...")
        asyncio.create_task(aria2_download_task(text, context, user_id))

    # 8. Cloudflare Tunnel Token
    elif state == 'waiting_cft_token':
        if len(text) < 20:
             await update.message.reply_text("⚠️ Token 似乎太短了，请检查是否完整复制。")
             return
        save_config({'cloudflared_token': text})
        await update.message.reply_text(
            "✅ **Tunnel Token 已保存**\n\n请点击 Alist 菜单中的 [🚇 启动穿透] 开启服务。", 
            parse_mode='Markdown'
        )
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
