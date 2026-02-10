import subprocess
import psutil
import socket
import os
from .alist import get_alist_pid, check_alist_version
from .stream import get_stream_status

def check_program_version(cmd):
    """通用程序版本检查"""
    try:
        if cmd == "ffmpeg":
            output = subprocess.check_output(["ffmpeg", "-version"], stderr=subprocess.STDOUT, text=True)
            return output.splitlines()[0].split()[2] 
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return None

def get_local_ip():
    """获取本机局域网 IP"""
    try:
        interfaces = psutil.net_if_addrs()
        priority_interfaces = ['wlan0', 'eth0', 'wlan1']
        for iface in priority_interfaces:
            if iface in interfaces:
                for snic in interfaces[iface]:
                    if snic.family == socket.AF_INET:
                        return snic.address
        exclude_prefixes = ('tun', 'ppp', 'lo', 'docker', 'veth', 'rmnet')
        for name, snics in interfaces.items():
            if name.lower().startswith(exclude_prefixes): continue
            for snic in snics:
                if snic.family == socket.AF_INET and not snic.address.startswith("127."):
                    return snic.address
        return "127.0.0.1"
    except Exception:
        return "127.0.0.1"

def get_all_ips():
    """获取所有可能的局域网 IP"""
    ips = []
    try:
        interfaces = psutil.net_if_addrs()
        for name, snics in interfaces.items():
            if name.lower().startswith(('lo', 'tun', 'rmnet')): continue
            for snic in snics:
                if snic.family == socket.AF_INET:
                    ips.append(f"{name}: {snic.address}")
    except:
        pass
    return ips

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"

def scan_local_videos():
    """扫描本地视频文件"""
    search_paths = [
        "/sdcard/Download",
        "/sdcard/Movies",
        "/sdcard/DCIM/Camera",
        os.getcwd() # 当前目录
    ]
    video_extensions = ('.mp4', '.mkv', '.avi', '.flv', '.mov', '.ts')
    found_files = []

    for path in search_paths:
        if not os.path.exists(path):
            continue
        try:
            # 仅扫描一级目录，避免卡顿
            with os.scandir(path) as it:
                for entry in it:
                    if entry.is_file() and entry.name.lower().endswith(video_extensions):
                        found_files.append({
                            "name": entry.name,
                            "path": entry.path,
                            "mtime": entry.stat().st_mtime,
                            "size": entry.stat().st_size
                        })
        except Exception:
            pass
    
    # 按修改时间倒序排列（最新的在前）
    found_files.sort(key=lambda x: x['mtime'], reverse=True)
    return found_files[:10] # 只返回最新的10个

def get_env_report():
    """生成环境报告文本"""
    ffmpeg_ver = check_program_version("ffmpeg")
    alist_ver = check_alist_version()
    alist_pid = get_alist_pid()
    stream_active = get_stream_status()
    local_ip = get_local_ip()
    
    cpu_usage = psutil.cpu_percent(interval=None)
    mem_info = psutil.virtual_memory()
    mem_usage = f"{mem_info.used / 1024 / 1024:.0f}MB / {mem_info.total / 1024 / 1024:.0f}MB"

    return (
        f"🖥 **服务器环境报告**\n\n"
        f"🌐 **局域网IP**: `{local_ip}`\n\n"
        f"🎥 **FFmpeg**:\n"
        f"• 安装状态: {'✅ ' + ffmpeg_ver if ffmpeg_ver else '❌ 未安装'}\n"
        f"• 推流任务: {'🔴 进行中' if stream_active else '⚪ 空闲'}\n\n"
        f"🗂 **Alist**:\n"
        f"• 安装状态: {'✅ ' + alist_ver if alist_ver else '❌ 未安装'}\n"
        f"• 运行状态: {'🟢 运行中 (PID ' + str(alist_pid) + ')' if alist_pid else '🔴 已停止'}\n\n"
        f"⚙️ **系统资源**:\n"
        f"• CPU: {cpu_usage}%\n"
        f"• 内存: {mem_usage}"
    )
