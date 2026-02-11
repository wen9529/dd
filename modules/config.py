import json
import os
import logging
import sys

# --- 核心配置 ---
# 请在此处填入您的 Token 和 ID，或者在 Web 界面/本地编辑器修改。
TOKEN = "7565918204:AAH3E3Bb9Op7Xv-kezL6GISeJj8mA6Ycwug" 
OWNER_ID = 1878794912
# Cloudflare Tunnel Token
CLOUDFLARED_TOKEN = "eyJhIjoiMjEyOGViYjhlN2Y2OTU4MjZkNzVmNjkwZTBhZTE4MjEiLCJ0IjoiYTE3OTBhNmMtMWQyZi00MDUzLTlkOTktOGMyZWUyZmJlNTczIiwicyI6Ik1UTXpaamhsT1RVdE1tTTJaaTAwWmpnMUxXSXlaakF0WldWa1lUVXhaR0V3TlRnMCJ9"

CONFIG_FILE = "bot_config.json"
FFMPEG_LOG_FILE = "ffmpeg.log"

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger("Config")

def is_owner(user_id):
    """检查用户是否为管理员"""
    uid_str = str(user_id).strip()
    owner_str = str(OWNER_ID).strip()
    return uid_str == owner_str

def load_config():
    """加载配置文件"""
    config = {}
    save_needed = False
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
    
    # --- 迁移逻辑：单一密钥 -> 多密钥列表 ---
    if 'stream_key' in config and 'stream_keys' not in config:
        old_key = config.get('stream_key')
        if old_key and old_key != "❌ 未设置":
            config['stream_keys'] = [{'name': '默认密钥', 'key': old_key}]
            config['active_key_index'] = 0
            logger.info("已将旧密钥迁移到多密钥列表")
            save_needed = True
        # 删除旧字段，避免混淆（可选，这里保留 clean）
        # del config['stream_key'] 

    # 确保基本结构存在
    if 'stream_keys' not in config:
        config['stream_keys'] = []
    if 'active_key_index' not in config:
        config['active_key_index'] = 0

    if save_needed:
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
        except:
            pass

    return {
        'token': config.get('token', TOKEN),
        'owner_id': config.get('owner_id', OWNER_ID),
        'rtmp': config.get('rtmp', None),
        'rtmp_server': config.get('rtmp_server', ''),
        # 返回多密钥结构
        'stream_keys': config.get('stream_keys', []),
        'active_key_index': config.get('active_key_index', 0),
        'alist_token': config.get('alist_token', ''),
        'cloudflared_token': config.get('cloudflared_token', CLOUDFLARED_TOKEN)
    }

def save_config(config_update):
    """保存配置文件"""
    try:
        current_config = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                current_config = json.load(f)
        
        current_config.update(config_update)
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(current_config, f, indent=4)
        logger.info("配置已保存")
    except Exception as e:
        logger.error(f"保存配置失败: {e}")
