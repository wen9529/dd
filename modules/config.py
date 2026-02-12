import json
import os
import logging
import sys
from dotenv import load_dotenv

# --- 加载环境变量 (.env) ---
# 策略：按优先级顺序加载，找不到则跳过
# 1. 加载当前项目目录下的 .env
load_dotenv()

# 2. 加载上级目录 (Termux 根目录/Home) 下的 .env
# 这是为了满足用户在项目外层管理配置的需求
parent_env = os.path.join(os.path.dirname(os.getcwd()), '.env')
if os.path.exists(parent_env):
    load_dotenv(parent_env)

# 3. 加载用户主目录下的 .env (作为备选)
home_env = os.path.expanduser('~/.env')
if os.path.exists(home_env):
    load_dotenv(home_env)

# --- 默认配置 ---
DEFAULT_TOKEN = "YOUR_BOT_TOKEN_HERE" 
DEFAULT_OWNER_ID = 0
# 用户指定的默认 Telegram 推流服务器
DEFAULT_RTMP_SERVER = "rtmps://dc5-1.rtmp.t.me/s/"

CONFIG_FILE = "bot_config.json"
FFMPEG_LOG_FILE = "ffmpeg.log"

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    stream=sys.stdout
)
logger = logging.getLogger("Config")

def is_owner(user_id):
    """检查用户是否为管理员"""
    uid_str = str(user_id).strip()
    
    # 优先从配置加载，其次从环境变量加载
    config = load_config()
    owner_id = config.get('owner_id', 0)
    
    return uid_str == str(owner_id).strip()

def load_config():
    """
    加载配置文件。
    优先级: 
    1. 环境变量 (包括 .env 文件)
    2. bot_config.json (本地运行，由菜单生成)
    3. 默认值 (代码中的占位符)
    """
    config = {}
    
    # 1. 尝试读取本地文件
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            
    # --- 迁移逻辑：单一密钥 -> 多密钥列表 ---
    # 检查环境变量中是否有密钥
    env_key = os.getenv('RTMP_STREAM_KEY')
    
    # 如果 config 中没有 keys，但环境变量有，则初始化
    if 'stream_keys' not in config:
        config['stream_keys'] = []

    # 如果环境变量有 key，且列表中不存在，则添加
    if env_key and not any(k['key'] == env_key for k in config['stream_keys']):
        config['stream_keys'].insert(0, {'name': 'Env密钥', 'key': env_key})

    # 旧的 json 结构迁移
    save_needed = False
    if 'stream_key' in config and not config['stream_keys']:
        old_key = config.get('stream_key')
        if old_key and old_key != "❌ 未设置":
            config['stream_keys'].append({'name': '默认密钥', 'key': old_key})
            save_needed = True

    if 'active_key_index' not in config:
        config['active_key_index'] = 0

    if save_needed:
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
        except:
            pass

    # 2. 合并环境变量 
    # 优先读取 RTMP_SERVER，如果没有则尝试读取 RTMP_URL (兼容用户习惯)
    env_rtmp_server = os.getenv('RTMP_SERVER') or os.getenv('RTMP_URL')
    
    final_config = {
        'token': os.getenv('BOT_TOKEN', config.get('token', DEFAULT_TOKEN)),
        'owner_id': int(os.getenv('OWNER_ID', config.get('owner_id', DEFAULT_OWNER_ID))),
        'rtmp': config.get('rtmp', None),
        # 优先级: 环境变量 -> 配置文件 -> 默认常量
        'rtmp_server': env_rtmp_server or config.get('rtmp_server', DEFAULT_RTMP_SERVER),
        'stream_keys': config.get('stream_keys', []),
        'active_key_index': config.get('active_key_index', 0),
        'alist_token': os.getenv('ALIST_TOKEN', config.get('alist_token', '')),
        'cloudflared_token': os.getenv('CLOUDFLARED_TOKEN', config.get('cloudflared_token', ''))
    }
    
    return final_config

def save_config(config_update):
    """保存配置文件到 bot_config.json"""
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