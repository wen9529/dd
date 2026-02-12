from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
import os

def get_main_menu_keyboard():
    """底部持久化主菜单 (Reply Keyboard)"""
    keyboard = [
        [KeyboardButton("☁️ 云盘浏览"), KeyboardButton("📥 离线下载")], 
        [KeyboardButton("🎵 音频+图片"), KeyboardButton("🔗 链接/Alist")],
        [KeyboardButton("🛑 停止推流"), KeyboardButton("⚙️ 设置"), KeyboardButton("🗂 Alist")],
        [KeyboardButton("📊 状态监控"), KeyboardButton("♻️ 重启机器人")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_alist_browser_keyboard(current_path, items, page=0):
    """
    生成 Alist 文件浏览器键盘
    current_path: 当前路径字符串
    items: 文件对象列表
    page: 当前页码
    """
    keyboard = []
    
    # 排序：文件夹在前，文件在后
    items.sort(key=lambda x: (not x['is_dir'], x['name']))
    
    # 分页设置
    PAGE_SIZE = 15
    total_items = len(items)
    total_pages = (total_items + PAGE_SIZE - 1) // PAGE_SIZE
    
    # 修正页码范围
    if page < 0: page = 0
    if page >= total_pages and total_pages > 0: page = total_pages - 1
    
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    display_items = items[start:end]
    
    for idx, item in enumerate(display_items):
        # 使用绝对索引作为 callback
        abs_idx = start + idx
        name = item['name']
        is_dir = item['is_dir']
        
        # 截断长文件名
        if len(name) > 30: name = name[:28] + ".."
        
        icon = "📂" if is_dir else "📄"
        callback = f"alist_go:{abs_idx}"
        
        keyboard.append([InlineKeyboardButton(f"{icon} {name}", callback_data=callback)])
    
    # 分页导航栏
    pager_row = []
    if total_pages > 1:
        if page > 0:
            pager_row.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"alist_page:{page-1}"))
        
        pager_row.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
        
        if page < total_pages - 1:
            pager_row.append(InlineKeyboardButton("下一页 ➡️", callback_data=f"alist_page:{page+1}"))
            
    if pager_row:
        keyboard.append(pager_row)
    
    # 功能导航栏
    nav_row = []
    if current_path != "/":
        nav_row.append(InlineKeyboardButton("🔙 上一级", callback_data="alist_up"))
    
    nav_row.append(InlineKeyboardButton("❌ 关闭", callback_data="btn_close"))
    keyboard.append(nav_row)
    
    return InlineKeyboardMarkup(keyboard)

def get_alist_file_actions_keyboard():
    """文件操作菜单"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📺 直播推流", callback_data="alist_act_stream")],
        [InlineKeyboardButton("📥 离线下载", callback_data="alist_act_download")],
        [InlineKeyboardButton("🔙 返回列表", callback_data="alist_act_back")]
    ])

# --- 以下保留 Inline 键盘用于子菜单和列表选择 ---

def get_settings_keyboard():
    """设置中心菜单 (Inline)"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📡 配置 RTMP 服务器", callback_data="btn_edit_server")],
        [InlineKeyboardButton("🔑 管理推流密钥", callback_data="btn_manage_keys")],
        [InlineKeyboardButton("🔐 配置 Alist Token", callback_data="btn_alist_token")],
        [InlineKeyboardButton("❌ 关闭菜单", callback_data="btn_close")]
    ])

def get_alist_keyboard(alist_running, cft_running):
    """Alist & 穿透 管理菜单 (Inline)"""
    # Alist 状态行
    a_icon = "🟢" if alist_running else "🔴"
    a_text = "停止 Alist" if alist_running else "启动 Alist"
    a_cb = "btn_alist_stop" if alist_running else "btn_alist_start"
    
    # Tunnel 状态行
    c_icon = "🟢" if cft_running else "⚪"
    c_text = "停止穿透" if cft_running else "启动穿透"
    c_cb = "btn_cft_toggle"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{a_icon} {a_text}", callback_data=a_cb)],
        [InlineKeyboardButton(f"🚇 {c_icon} {c_text}", callback_data=c_cb), InlineKeyboardButton("🔑 设置穿透 Token", callback_data="btn_cft_token")],
        [InlineKeyboardButton("💾 一键挂载本机存储", callback_data="btn_alist_mount_local")],
        [InlineKeyboardButton("ℹ️ 获取访问地址", callback_data="btn_alist_info"), InlineKeyboardButton("👀 查看管理员账号", callback_data="btn_alist_admin")],
        [InlineKeyboardButton("📝 重置登录密码", callback_data="btn_alist_set_pwd"), InlineKeyboardButton("🔧 修复局域网访问", callback_data="btn_alist_fix")],
        [InlineKeyboardButton("❌ 关闭菜单", callback_data="btn_close")]
    ])

def get_keys_management_keyboard(keys, active_index, delete_mode=False):
    """密钥管理菜单 (Inline)"""
    keyboard = []
    
    if delete_mode:
        keyboard.append([InlineKeyboardButton("👇 点击按钮删除对应密钥", callback_data="noop")])
    
    for idx, key_data in enumerate(keys):
        name = key_data.get('name', '未命名')
        if delete_mode:
            btn_text = f"❌ 删除: {name}"
            callback = f"delete_key_{idx}"
        else:
            status = "✅" if idx == active_index else "⚪"
            btn_text = f"{status} {name}"
            callback = f"select_key_{idx}"
        
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=callback)])

    if not delete_mode:
        keyboard.append([
            InlineKeyboardButton("➕ 新增密钥", callback_data="btn_add_key"),
            InlineKeyboardButton("🗑️ 进入删除模式", callback_data="btn_del_key_mode")
        ])
    else:
        keyboard.append([InlineKeyboardButton("🔙 返回列表", callback_data="btn_manage_keys")])

    keyboard.append([InlineKeyboardButton("🔙 返回设置", callback_data="btn_menu_settings")])
    return InlineKeyboardMarkup(keyboard)

def get_download_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 查看正在下载的任务", callback_data="btn_check_downloads")],
        [InlineKeyboardButton("❌ 关闭", callback_data="btn_close")]
    ])

def get_back_keyboard(target="main"):
    """通用的返回按钮"""
    if target == "main":
         return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 关闭", callback_data="btn_close")]])
    # 针对不同场景的返回
    callback = "btn_menu_settings" if target == "settings" else "btn_close"
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data=callback)]])