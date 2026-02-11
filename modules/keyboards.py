from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_main_keyboard(is_streaming=False):
    """主菜单键盘"""
    if is_streaming:
        # 推流中：显示控制面板
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🛑 停止当前推流", callback_data="btn_stop_stream_quick")],
            [InlineKeyboardButton("📜 实时日志", callback_data="btn_view_log"), InlineKeyboardButton("📊 流量监控", callback_data="btn_env")],
            [InlineKeyboardButton("🔄 刷新状态", callback_data="btn_refresh")]
        ])
    else:
        # 空闲状态：显示功能菜单
        return InlineKeyboardMarkup([
            # 第一行：核心功能 (大按钮)
            [InlineKeyboardButton("🚀 开始推流 / 选择资源", callback_data="btn_menu_stream_select")],
            
            # 第二行：次要功能
            [InlineKeyboardButton("🗂 Alist 网盘", callback_data="btn_alist"), InlineKeyboardButton("⚙️ 系统设置", callback_data="btn_menu_settings")],
            
            # 第三行：系统维护
            [InlineKeyboardButton("♻️ 检查更新", callback_data="btn_update"), InlineKeyboardButton("📊 状态监控", callback_data="btn_env")]
        ])

def get_stream_start_keyboard():
    """推流源选择菜单"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 输入链接 / Alist 路径", callback_data="btn_start_stream")],
        [InlineKeyboardButton("📂 本地视频文件", callback_data="btn_local_stream")],
        [InlineKeyboardButton("🎵 本地音频 + 图片", callback_data="btn_audio_stream")],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="btn_back_main")]
    ])

def get_settings_keyboard():
    """设置中心菜单"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📡 配置 RTMP 服务器", callback_data="btn_edit_server")],
        [InlineKeyboardButton("🔑 管理推流密钥", callback_data="btn_manage_keys")],
        [InlineKeyboardButton("🔐 配置 Alist Token", callback_data="btn_alist_token")],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="btn_back_main")]
    ])

def get_alist_keyboard(is_running):
    """Alist 管理菜单"""
    status_icon = "🟢" if is_running else "🔴"
    action_text = "停止服务" if is_running else "启动服务"
    action_callback = "btn_alist_stop" if is_running else "btn_alist_start"
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{status_icon} {action_text}", callback_data=action_callback)],
        [InlineKeyboardButton("ℹ️ 获取访问地址", callback_data="btn_alist_info"), InlineKeyboardButton("👀 查看管理员账号", callback_data="btn_alist_admin")],
        [InlineKeyboardButton("📝 重置登录密码", callback_data="btn_alist_set_pwd"), InlineKeyboardButton("🔧 修复局域网访问", callback_data="btn_alist_fix")],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="btn_back_main")]
    ])

def get_keys_management_keyboard(keys, active_index, delete_mode=False):
    """密钥管理菜单"""
    keyboard = []
    
    # 标题行
    if delete_mode:
        keyboard.append([InlineKeyboardButton("👇 点击按钮删除对应密钥", callback_data="noop")])
    
    # 列表显示密钥
    for idx, key_data in enumerate(keys):
        name = key_data.get('name', '未命名')
        if delete_mode:
            # 删除模式
            btn_text = f"❌ 删除: {name}"
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
            InlineKeyboardButton("➕ 新增密钥", callback_data="btn_add_key"),
            InlineKeyboardButton("🗑️ 进入删除模式", callback_data="btn_del_key_mode")
        ])
    else:
        keyboard.append([InlineKeyboardButton("🔙 完成删除 / 返回", callback_data="btn_manage_keys")])

    keyboard.append([InlineKeyboardButton("🔙 返回设置中心", callback_data="btn_menu_settings")])
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard(target="main"):
    """通用的返回按钮"""
    callback = "btn_back_main"
    if target == "stream_select":
        callback = "btn_menu_stream_select"
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 返回", callback_data=callback)]])
