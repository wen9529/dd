from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

def get_main_menu_keyboard():
    """底部持久化主菜单 (Reply Keyboard)"""
    keyboard = [
        [KeyboardButton("📺 本地视频"), KeyboardButton("🎵 音频+图片"), KeyboardButton("🔗 链接/Alist")],
        [KeyboardButton("🛑 停止推流"), KeyboardButton("⚙️ 设置"), KeyboardButton("🗂 Alist")],
        [KeyboardButton("📊 状态监控"), KeyboardButton("♻️ 重启机器人")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

# --- 以下保留 Inline 键盘用于子菜单和列表选择 ---

def get_settings_keyboard():
    """设置中心菜单 (Inline)"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📡 配置 RTMP 服务器", callback_data="btn_edit_server")],
        [InlineKeyboardButton("🔑 管理推流密钥", callback_data="btn_manage_keys")],
        [InlineKeyboardButton("🔐 配置 Alist Token", callback_data="btn_alist_token")],
        [InlineKeyboardButton("❌ 关闭菜单", callback_data="btn_close")]
    ])

def get_alist_keyboard(is_running):
    """Alist 管理菜单 (Inline)"""
    status_icon = "🟢" if is_running else "🔴"
    action_text = "停止服务" if is_running else "启动服务"
    action_callback = "btn_alist_stop" if is_running else "btn_alist_start"
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{status_icon} {action_text}", callback_data=action_callback)],
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

def get_back_keyboard(target="main"):
    """通用的返回按钮"""
    if target == "main":
         return InlineKeyboardMarkup([[InlineKeyboardButton("❌ 关闭", callback_data="btn_close")]])
    # 针对不同场景的返回
    callback = "btn_menu_settings" if target == "settings" else "btn_close"
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data=callback)]])
