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
        [InlineKeyboardButton("📝 修改推流地址", callback_data="btn_edit_server"), InlineKeyboardButton("🔑 修改推流密钥", callback_data="btn_edit_key")],
        [InlineKeyboardButton("📜 查看推流日志", callback_data="btn_view_log")],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="btn_back_main")]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回主菜单", callback_data="btn_back_main")]])
