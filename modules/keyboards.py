from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 链接推流", callback_data="btn_start_stream"), InlineKeyboardButton("📂 本地视频", callback_data="btn_local_stream")],
        [InlineKeyboardButton("🎵 音频推流", callback_data="btn_audio_stream"), InlineKeyboardButton("📺 推流设置", callback_data="btn_stream_settings")],
        [InlineKeyboardButton("🗂 Alist 管理", callback_data="btn_alist"), InlineKeyboardButton("♻️ 检查更新", callback_data="btn_update")],
        [InlineKeyboardButton("🔍 环境自检", callback_data="btn_env"), InlineKeyboardButton("🔄 刷新菜单", callback_data="btn_refresh")]
    ])

def get_alist_keyboard(is_running):
    start_stop_btn = InlineKeyboardButton("🔴 停止服务", callback_data="btn_alist_stop") if is_running else InlineKeyboardButton("🟢 启动服务", callback_data="btn_alist_start")
    return InlineKeyboardMarkup([
        [start_stop_btn],
        [InlineKeyboardButton("ℹ️ 访问地址", callback_data="btn_alist_info"), InlineKeyboardButton("🔐 设置 Token", callback_data="btn_alist_token")],
        [InlineKeyboardButton("🔑 查看账号", callback_data="btn_alist_admin"), InlineKeyboardButton("📝 重置密码", callback_data="btn_alist_set_pwd")],
        [InlineKeyboardButton("🔧 修复局域网", callback_data="btn_alist_fix"), InlineKeyboardButton("🔙 返回主菜单", callback_data="btn_back_main")]
    ])

def get_stream_settings_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 修改推流地址", callback_data="btn_edit_server")],
        [InlineKeyboardButton("🔑 管理推流密钥", callback_data="btn_manage_keys")],
        [InlineKeyboardButton("📜 查看推流日志", callback_data="btn_view_log")],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="btn_back_main")]
    ])

def get_keys_management_keyboard(keys, active_index, delete_mode=False):
    keyboard = []
    
    # 列表显示密钥
    for idx, key_data in enumerate(keys):
        name = key_data.get('name', '未命名')
        if delete_mode:
            # 删除模式
            btn_text = f"🗑️ {name}"
            callback = f"delete_key_{idx}"
        else:
            # 选择模式
            status = "✅" if idx == active_index else "⚪"
            btn_text = f"{status} {name}"
            callback = f"select_key_{idx}"
        
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=callback)])

    # 操作栏
    if not delete_mode:
        keyboard.append([
            InlineKeyboardButton("➕ 添加密钥", callback_data="btn_add_key"),
            InlineKeyboardButton("🗑️ 删除密钥", callback_data="btn_del_key_mode")
        ])
    else:
        keyboard.append([InlineKeyboardButton("🔙 退出删除模式", callback_data="btn_manage_keys")])

    keyboard.append([InlineKeyboardButton("🔙 返回设置", callback_data="btn_stream_settings")])
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回主菜单", callback_data="btn_back_main")]])
