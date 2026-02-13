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
        # 建议使用 pm2 restart termux-tunnel 来管理，这里保留纯 Python 启动方式备用
        cmd = ["cloudflared", "tunnel", "run", "--token", token]
        
        # 启动进程 (使用 nohup 方式模拟)
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

def get_cloudflared_log(lines=15):
    """读取 Cloudflared 日志 (由 setup.sh 配置在 logs/tunnel_err.log)"""
    log_path = os.path.join(os.getcwd(), "logs", "tunnel_err.log")
    
    if not os.path.exists(log_path):
        return "⚠️ 日志文件不存在，请运行 `bash setup.sh` 重建环境。"
        
    try:
        # 读取最后 N 行
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            # 简单实现：读取所有行取最后部分 (日志文件通常不会太大，因为 PM2 会轮转)
            all_lines = f.readlines()
            if not all_lines:
                return "日志为空，Tunnel 可能正在启动..."
            return "".join(all_lines[-lines:])
    except Exception as e:
        return f"读取失败: {e}"
