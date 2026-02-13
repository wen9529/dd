import logging
import asyncio
import subprocess
import os
import signal
import sys
import time
from urllib.parse import quote
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# --- 导入模块 ---
# 注意：不要导入 TOKEN，它应该通过 load_config() 动态获取
from modules.config import load_config, save_config, is_owner, CONFIG_FILE
from modules.utils import (
    get_local_ip, get_all_ips, get_env_report, scan_local_audio, scan_local_images, 
    format_size, run_shell_command, run_speedtest_sync
)
from modules.alist import get_alist_pid, fix_alist_config, alist_list_files, mount_local_storage
from modules.cloudflared import get_cloudflared_pid, start_cloudflared, stop_cloudflared
from modules.stream import run_ffmpeg_stream, stop_ffmpeg_process, get_stream_status, get_log_content, kill_zombie_processes
from modules.downloader import aria2_download_task, get_active_downloads
from modules.keyboards import (
    get_main_menu_keyboard,
    get_alist_keyboard, 
    get_settings_keyboard, 
    get_back_keyboard, 
    get_keys_management_keyboard,
    get_alist_browser_keyboard,
    get_alist_file_actions_keyboard,
    get_download_menu_keyboard
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
        
        # 标记默认封面
        prefix = "🖼 "
        if img.get('is_default'):
            prefix = "🌐 "
            
        btn_text = f"{mark} {prefix}{img['name']}"
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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """帮助菜单"""
    if not is_owner(update.effective_user.id): return
    
    help_text = (
        "📘 **Termux Bot 帮助文档**\n\n"
        "🎮 **基础指令**:\n"
        "• `/start` - 呼出底部菜单\n"
        "• `/stopstream` - 强制停止推流\n"
        "• `/speedtest` - 网络测速\n"
        "• `/cmd <命令>` - 执行 Termux 命令\n\n"
        "⚙️ **配置指令**:\n"
        "• `/settoken <Token>` - 修改 Bot Token\n"
        "• `/setowner <ID>` - 修改管理员 ID\n\n"
        "📺 **推流模式**:\n"
        "1. **直接回复链接** - 自动开始推流\n"
        "2. **回复 Alist 路径** - 例如 `/电影/aaa.mp4`\n"
        "3. **菜单操作** - 点击 [云盘浏览] 或 [音频+图片]\n\n"
        "🛠 **维护**:\n"
        "• 配置修改后建议点击 [♻️ 重启机器人]\n"
        "• 无法连接 Alist 时尝试菜单中的 [🔧 修复]\n"
        "• 记得运行 `termux-wake-lock` 防止断网"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def set_token_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """修改 Token 指令"""
    if not is_owner(update.effective_user.id): return
    
    if not context.args:
        await update.message.reply_text("💡 用法: `/settoken <新Token>`")
        return
        
    new_token = context.args[0].strip()
    if ":" not in new_token:
        await update.message.reply_text("⚠️ Token 格式似乎不正确 (应包含 ':')")
        return

    save_config({'token': new_token})
    
    await update.message.reply_text(
        f"✅ **Token 已更新**\n\n"
        f"新 Token: `{new_token}`\n"
        "请点击下方 [♻️ 重启机器人] 使其生效。",
        parse_mode='Markdown'
    )

async def set_owner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """修改 Owner ID 指令"""
    if not is_owner(update.effective_user.id): return
    
    if not context.args:
        await update.message.reply_text("💡 用法: `/setowner <用户ID>`")
        return
        
    try:
        new_id = int(context.args[0].strip())
        save_config({'owner_id': new_id})
        
        await update.message.reply_text(
            f"✅ **管理员 ID 已更新**\n\n"
            f"新 ID: `{new_id}`\n"
            "请点击下方 [♻️ 重启机器人] 使其生效。",
            parse_mode='Markdown'
        )
    except ValueError:
        await update.message.reply_text("❌ ID 必须是数字")

async def cmd_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /cmd 或 /sh 命令"""
    if not is_owner(update.effective_user.id): return
    
    if not context.args:
        await update.message.reply_text("💡 用法: `/cmd <命令>`\n例如: `/cmd ls -la`", parse_mode='Markdown')
        return

    cmd = " ".join(context.args)
    status_msg = await update.message.reply_text(f"⏳ 执行中: `{cmd}`...", parse_mode='Markdown')
    
    result = await run_shell_command(cmd)
    
    # 优化：如果输出过长，发送文件
    if len(result) > 3000:
        file_path = "cmd_output.txt"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(result)
        
        await status_msg.delete()
        await update.message.reply_document(
            document=open(file_path, "rb"), 
            caption=f"💻 命令 `{cmd}` 执行结果 (输出过长)",
            filename="output.txt"
        )
        os.remove(file_path)
    else:
        await status_msg.edit_text(f"💻 **执行结果**:\n```bash\n{result}\n```", parse_mode='Markdown')

async def speedtest_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理测速命令"""
    if not is_owner(update.effective_user.id): return
    
    status_msg = await update.message.reply_text("⚡ 正在测速，请稍候 (约需 10-20秒)...")
    
    # 在线程中运行同步的 speedtest，避免阻塞 bot 主循环
    loop = asyncio.get_event_loop()
    success, result = await loop.run_in_executor(None, run_speedtest_sync)
    
    await status_msg.edit_text(f"📊 **测速结果**\n\n{result}")

# --- Alist 浏览逻辑核心 ---
async def update_alist_browser(query, context, path, page=0):
    """刷新文件浏览消息"""
    # 检查是否是同一路径的翻页操作 (使用缓存)
    cached_path = context.user_data.get('alist_path')
    cached_items = context.user_data.get('alist_items')
    
    if path == cached_path and cached_items:
        items = cached_items
    else:
        success, items = alist_list_files(path)
        if not success:
            await query.answer(f"❌ 读取失败: {items}", show_alert=True)
            return
        context.user_data['alist_path'] = path
        context.user_data['alist_items'] = items

    # 排序并生成键盘
    keyboard = get_alist_browser_keyboard(path, items, page=page)
    
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
    
    # --- 测速 ---
    if data == "btn_run_speedtest":
        await query.edit_message_text("⚡ 正在测速，请稍候 (约需 10-20秒)...")
        loop = asyncio.get_event_loop()
        success, result = await loop.run_in_executor(None, run_speedtest_sync)
        
        # 重新添加查看日志按钮
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回状态", callback_data="btn_refresh_status")]])
        await query.edit_message_text(f"📊 **测速结果**\n\n{result}", reply_markup=keyboard)
        return
        
    if data == "btn_refresh_status":
        # 获取状态报告 (现在是异步)
        text = await get_env_report()
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡ 开始测速", callback_data="btn_run_speedtest")],
            [InlineKeyboardButton("📜 查看实时日志", callback_data="btn_view_log")],
            [InlineKeyboardButton("❌ 关闭", callback_data="btn_close")]
        ])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')
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
                    await update_alist_browser(query, context, new_path, page=0)
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

    elif data.startswith("alist_page:"):
        # 翻页处理
        try:
            page = int(data.split(":")[1])
            current_path = context.user_data.get('alist_path', "/")
            await update_alist_browser(query, context, current_path, page=page)
        except:
            pass

    elif data == "alist_up":
        current_path = context.user_data.get('alist_path', "/")
        if current_path != "/":
            parent_path = os.path.dirname(current_path.rstrip("/"))
            if not parent_path: parent_path = "/"
            await update_alist_browser(query, context, parent_path, page=0)
        else:
            await query.answer("已经是根目录了", show_alert=True)

    elif data == "alist_act_back":
        # 返回当前目录列表 (重置为第一页)
        path = context.user_data.get('alist_path', "/")
        await update_alist_browser(query, context, path, page=0)

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
        # Alist 下载 (Aria2 离线下载)
        file_path = context.user_data.get('alist_selected_path')
        if not file_path: return
        encoded_path = quote(file_path, safe='/')
        
        # 使用本地 URL 进行下载，因为 Aria2 和 Alist 在同一台设备上，速度最快
        config = load_config()
        local_host = config.get('alist_host', "http://127.0.0.1:5244")
        full_url = f"{local_host}/d{encoded_path}"
        
        await query.edit_message_text("🚀 已添加到后台下载队列", parse_mode='Markdown')
        asyncio.create_task(aria2_download_task(full_url, context, user_id))
        
    elif data == "btn_check_downloads":
        tasks = get_active_downloads()
        if not tasks:
            text = "💤 当前没有正在进行的下载任务"
        else:
            text = "📥 **正在下载的任务**:\n\n" + "\n".join(tasks)
        
        await query.edit_message_text(text, reply_markup=get_back_keyboard("main"), parse_mode='Markdown')

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
        # 使用 getattr 安全获取，防止 key 不存在
        audios = context.user_data.get('local_audios', [])
        
        if 0 <= idx < len(audios):
             context.user_data['temp_audio'] = audios[idx]['path']
             context.user_data['temp_audio_name'] = audios[idx]['name']
             
             await query.edit_message_text("🔍 正在扫描图片 (异步)...")
             
             # 异步调用图片扫描，防止阻塞
             loop = asyncio.get_event_loop()
             images = await loop.run_in_executor(None, scan_local_images)
             
             # 如果配置了默认封面，且图片列表可能为空，或者用户想用默认封面
             config = load_config()
             default_cover = config.get('default_cover')
             if default_cover and default_cover.startswith("http"):
                 # 添加一个虚拟的图片对象
                 images.insert(0, {
                     "name": "使用默认封面",
                     "path": default_cover,
                     "is_default": True
                 })

             context.user_data['local_images'] = images
             context.user_data['selected_img_indices'] = set()
             
             if not images:
                 await query.edit_message_text("⚠️ 未找到图片，且未配置默认封面 (.env DEFAULT_COVER)", reply_markup=get_back_keyboard("main"))
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
            
            bg_arg = selected_image_paths
            if len(selected_image_paths) == 1:
                bg_arg = selected_image_paths[0]

            await query.edit_message_text("🚀 正在请求推流进程...", parse_mode='Markdown')
            await run_ffmpeg_stream(update, audio_path, background_image=bg_arg)
            
            # 清理状态
            if 'temp_audio' in context.user_data: del context.user_data['temp_audio']
            if 'selected_img_indices' in context.user_data: del context.user_data['selected_img_indices']
            
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
    
    elif data == "btn_alist_mount_local":
        await query.answer("⏳ 正在请求 API 挂载存储...")
        success, msg = await mount_local_storage()
        if success:
             await query.message.reply_text(msg)
        else:
             await query.message.reply_text(f"❌ 挂载失败: {msg}\n\n请确保 Alist 已启动且 Token 配置正确。")

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
        config = load_config()
        local_ip = get_local_ip()
        all_ips = get_all_ips()
        ip_list_text = "\n".join([f"• `{ip}`" for ip in all_ips]) if all_ips else f"• `{local_ip}`"
        
        cft_pid = get_cloudflared_pid()
        tunnel_status = "🟢 运行中" if cft_pid else "⚪ 未运行"
        
        public_url = config.get('alist_public_url', "未配置")
        
        await context.bot.send_message(
            chat_id=user_id, 
            text=f"🌐 **Alist 访问地址**:\n\n🌍 **公网 (Tunnel)**:\n`{public_url}`\n\n📱 **本机 (Local)**:\n`http://127.0.0.1:5244`\n\n📡 **局域网 (LAN)**:\n{ip_list_text}\n\n🚇 **穿透进程**: {tunnel_status}", 
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
        
        # 添加下载日志按钮
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 下载完整日志文件", callback_data="btn_dl_log")],
            [InlineKeyboardButton("❌ 关闭", callback_data="btn_close")]
        ])
        
        await context.bot.send_message(
            chat_id=user_id, 
            text=f"📜 **实时日志** (后3000字符):\n\n```\n{log_content}\n```", 
            parse_mode='Markdown',
            reply_markup=keyboard
        )

    elif data == "btn_dl_log":
        # 下载日志文件
        files_to_send = ["logs/bot_out.log", "logs/bot_err.log"]
        sent_count = 0
        for fpath in files_to_send:
            if os.path.exists(fpath):
                await context.bot.send_document(chat_id=user_id, document=open(fpath, "rb"), caption=f"📄 {fpath}")
                sent_count += 1
        
        if sent_count == 0:
            await query.answer("⚠️ 未找到日志文件", show_alert=True)
        else:
             await query.answer("✅ 日志已发送")
        
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
        report = await get_env_report() # 现在是异步
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡ 开始测速", callback_data="btn_run_speedtest")],
            [InlineKeyboardButton("📜 查看实时日志", callback_data="btn_view_log")],
            [InlineKeyboardButton("❌ 关闭", callback_data="btn_close")]
        ])
        await update.message.reply_text(report, reply_markup=keyboard, parse_mode='Markdown')
        return

    if text == "♻️ 重启机器人":
        context.user_data['state'] = None
        
        await update.message.reply_text(
            "♻️ **系统智能更新系统**\n\n"
            "⚠️ **注意**: 系统将强制拉取云端代码覆盖本地。\n"
            "⏳ **流程**: 备份 -> 强制更新 -> 重启 -> 健康检查\n"
            "🛡️ **安全**: 如果更新后启动失败，系统将自动回滚。\n\n"
            "🚀 正在后台执行，请稍候...", 
            parse_mode='Markdown'
        )
        
        # 强制保存配置，防止覆盖时丢失
        curr_config = load_config()
        save_config({'token': curr_config['token'], 'owner_id': curr_config['owner_id']})
        
        # 使用 --force 参数确保即使 hash 一样也重装依赖和重启
        subprocess.Popen("nohup bash setup.sh --force > logs/update_trigger.log 2>&1 &", shell=True)
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
            "文件将保存到 `/sdcard/Download`。\n",
            parse_mode='Markdown',
            reply_markup=get_download_menu_keyboard()
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
        
        # 初始页码为 0
        keyboard = get_alist_browser_keyboard("/", items, page=0)
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
    
    msg_handle = None
    if query: 
        # await query.answer("🔍 正在扫描...") # 可选
        await query.edit_message_text("🔍 正在扫描本地音乐 (异步)...", parse_mode='Markdown')
    else: 
        msg_handle = await target.reply_text("🔍 正在扫描本地音乐 (异步)...", parse_mode='Markdown')
    
    # 关键修改：使用 executor 运行同步的 scan_local_audio，防止阻塞主循环
    loop = asyncio.get_event_loop()
    audios = await loop.run_in_executor(None, scan_local_audio)
    
    if not audios:
         text = "❌ **未找到音频文件**\n请检查 `/sdcard/Music` 或 `/sdcard/Download` 目录。"
         if query: await query.edit_message_text(text, parse_mode='Markdown')
         elif msg_handle: await msg_handle.edit_text(text, parse_mode='Markdown')
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
    markup = InlineKeyboardMarkup(keyboard)
    
    if query: await query.edit_message_text(text, reply_markup=markup, parse_mode='Markdown')
    elif msg_handle: await msg_handle.edit_text(text, reply_markup=markup, parse_mode='Markdown')


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
    
    # 启动时清理僵尸进程
    kill_zombie_processes()

    config = load_config()
    final_token = config.get('token')
    
    # --- 防崩溃机制 ---
    if final_token == "YOUR_BOT_TOKEN_HERE" or not final_token:
        print("❌ 错误: TOKEN 未配置！")
        print("⚠️ 机器人进入[休眠模式]以防止 PM2 无限重启。")
        print("   请编辑 .env 文件或 bot_config.json 填入正确的 Token。")
        while True:
             time.sleep(60)
             print("💤 [休眠中] 等待配置更新... 请使用 'pm2 stop termux-bot' 停止，或编辑 .env 后重启。")
        return

    try:
        application = ApplicationBuilder().token(final_token).build()
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command)) # 添加帮助指令
        application.add_handler(CommandHandler("stream", start_stream_cmd))
        application.add_handler(CommandHandler("stopstream", stop_stream_cmd))
        application.add_handler(CommandHandler("cmd", cmd_handler)) # Shell CMD Handler
        application.add_handler(CommandHandler("sh", cmd_handler))  # Alias
        application.add_handler(CommandHandler("speedtest", speedtest_handler)) # Speedtest handler
        
        # 新增的配置指令
        application.add_handler(CommandHandler("settoken", set_token_command))
        application.add_handler(CommandHandler("setowner", set_owner_command))
        
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
        application.add_handler(CallbackQueryHandler(button_callback))
        
        print("✅ 服务已就绪，按 Ctrl+C 停止")
        application.run_polling()
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        # 如果是网络错误等临时问题，稍微等待再退出，防止快速闪退
        time.sleep(5)

if __name__ == '__main__':
    main()