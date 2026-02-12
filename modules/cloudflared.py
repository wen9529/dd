import subprocess
import psutil
import os
import signal
from .config import load_config

def get_cloudflared_pid():
    """查找 cloudflared 进程 PID (仅限 tunnel run 模式)"""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'cloudflared' in proc.info['name']:
                cmdline = proc.info.get('cmdline', [])
                if 'tunnel' in cmdline and 'run' in cmdline:
                    return proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None

def start_cloudflared():
    """启动 Cloudflare Tunnel"""
    if get_cloudflared_pid():
        return True, "已经运行中"

    config = load_config()
    token = config.get('cloudflared_token', '')

    if not token or len(token) < 20:
        return False, "未配置 Tunnel Token"

    try:
        # cloudflared tunnel run --token xxx
        cmd = ["cloudflared", "tunnel", "run", "--token", token]
        
        # 启动进程，丢弃日志以防填满 buffer
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        return True, "启动命令已发送"
    except Exception as e:
        return False, str(e)

def stop_cloudflared():
    """停止 Cloudflare Tunnel"""
    pid = get_cloudflared_pid()
    if not pid:
        return False, "未运行"
    
    try:
        os.kill(pid, signal.SIGTERM)
        return True, "已停止"
    except Exception as e:
        return False, str(e)
