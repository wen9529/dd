import json
import os
import logging
import sys

# --- 核心配置 ---
# 请在此处填入您的 Token 和 ID，或者在 Web 界面/本地编辑器修改。
TOKEN = "7565918204:AAH3E3Bb9Op7Xv-kezL6GISeJj8mA6Ycwug" 
OWNER_ID = 1878794912

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
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
    
    return {
        'token': config.get('token', TOKEN),
        'owner_id': config.get('owner_id', OWNER_ID),
        'rtmp': config.get('rtmp', None),
        'rtmp_server': config.get('rtmp_server', ''),
        'stream_key': config.get('stream_key', ''),
        'alist_token': config.get('alist_token', '')
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
