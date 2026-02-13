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
parent_env = os.path.join(os.path.dirname(os.getcwd()), '.env')
if os.path.exists(parent_env):
    load_dotenv(parent_env)

# 3. 加载用户主目录下的 .env
home_env = os.path.expanduser('~/.env')
if os.path.exists(home_env):
    load_dotenv(home_env)

# --- 默认配置 ---
DEFAULT_TOKEN = "YOUR_BOT_TOKEN_HERE" 
DEFAULT_OWNER_ID = 0
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
    config = load_config()
    owner_id = config.get('owner_id', 0)
    return uid_str == str(owner_id).strip()

def load_config():
    """
    加载配置文件。
    兼容新旧环境变量名称。
    """
    config = {}
    
    # 1. 尝试读取本地文件
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            
    # --- 迁移与初始化逻辑 ---
    if 'stream_keys' not in config:
        config['stream_keys'] = []

    if 'active_key_index' not in config:
        config['active_key_index'] = 0

    # 2. 环境变量映射 (支持 TG_ 前缀的新变量)
    # Token: TG_BOT_TOKEN > BOT_TOKEN
    env_token = os.getenv('TG_BOT_TOKEN') or os.getenv('BOT_TOKEN')
    
    # Owner: TG_ADMIN_ID > OWNER_ID
    env_owner = os.getenv('TG_ADMIN_ID') or os.getenv('OWNER_ID')
    
    # RTMP: RTMP_URL > RTMP_SERVER
    env_rtmp = os.getenv('RTMP_URL') or os.getenv('RTMP_SERVER')

    # Alist
    env_alist_host = os.getenv('ALIST_HOST')
    # 优先使用环境变量中的 ALIST_PUBLIC_URL，其次是配置文件，最后回退到 ALIST_HOST (本地)
    env_alist_public = os.getenv('ALIST_PUBLIC_URL')
    
    final_config = {
        'token': env_token or config.get('token', DEFAULT_TOKEN),
        'owner_id': int(env_owner or config.get('owner_id', DEFAULT_OWNER_ID)),
        'rtmp': config.get('rtmp', None),
        'rtmp_server': env_rtmp or config.get('rtmp_server', DEFAULT_RTMP_SERVER),
        'stream_keys': config.get('stream_keys', []),
        'active_key_index': config.get('active_key_index', 0),
        
        # Alist 配置
        'alist_host': env_alist_host or config.get('alist_host', 'http://127.0.0.1:5244'),
        'alist_token': os.getenv('ALIST_TOKEN', config.get('alist_token', '')),
        'alist_user': os.getenv('ALIST_USER', config.get('alist_user', 'admin')),
        'alist_password': os.getenv('ALIST_PASSWORD', config.get('alist_password', '')),
        
        # Git / AutoUpdate 配置
        'github_owner': os.getenv('GITHUB_OWNER', config.get('github_owner', '')),
        'github_repo': os.getenv('GITHUB_REPO', config.get('github_repo', '')),
        'github_pat': os.getenv('GITHUB_PAT', config.get('github_pat', '')),

        # 其他
        'cloudflared_token': os.getenv('CLOUDFLARED_TOKEN', config.get('cloudflared_token', '')),
        'default_cover': os.getenv('DEFAULT_COVER', config.get('default_cover', '')),
        
        # 高级推流配置
        'stream_width': int(os.getenv('STREAM_WIDTH', config.get('stream_width', 1280))),
        'stream_height': int(os.getenv('STREAM_HEIGHT', config.get('stream_height', 720))),
        'stream_fps': int(os.getenv('STREAM_FPS', config.get('stream_fps', 25))),
        'stream_preset': os.getenv('STREAM_PRESET', config.get('stream_preset', 'veryfast')),
        'stream_bitrate': os.getenv('STREAM_BITRATE', config.get('stream_bitrate', '2000k')),
    }
    
    # 延迟绑定 public_url，确保能读取到 alist_host
    final_config['alist_public_url'] = env_alist_public or config.get('alist_public_url', final_config['alist_host'])
    
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