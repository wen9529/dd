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

def _scan_files(extensions, extra_paths=[]):
    """通用的文件扫描函数 (增强版 - 支持中文路径与更多目录)"""
    home = os.path.expanduser("~")
    
    # 扩展搜索路径
    search_paths = [
        # 1. 常见 App 音乐目录 (针对国产软件优化)
        "/sdcard/netease/cloudmusic/Music",  # 网易云
        "/sdcard/qqmusic/song",              # QQ音乐
        "/sdcard/kgmusic/download",          # 酷狗
        "/sdcard/kuwo/music",                # 酷我

        # 2. 标准 Android 路径
        "/sdcard/Music",
        "/sdcard/Download",
        "/sdcard/Movies",
        "/sdcard/Pictures",
        "/sdcard/DCIM",
        "/sdcard/Telegram",
        "/sdcard/WeiXin",
        "/sdcard/Tencent/QQfile_recv",
        
        # 3. 根目录 (用于捕获 /sdcard/我的音乐 这种自定义文件夹)
        "/sdcard",

        # 4. Termux 映射路径 (包含外部 SD 卡)
        os.path.join(home, "storage", "shared"),
        os.path.join(home, "storage", "music"),
        os.path.join(home, "storage", "downloads"),
        os.path.join(home, "storage", "external-1"), # 外部 SD 卡
        
        # 5. 机器人当前目录
        os.getcwd()
    ] + extra_paths
    
    found_files = []
    seen_paths = set() # 用于去重

    # 需要排除的系统目录，防止扫描耗时过长或无权限
    exclude_dirs = {'Android', 'LOST.DIR', 'System Volume Information', 'MIUI', 'data', 'obb'}

    for base_path in search_paths:
        if not os.path.exists(base_path):
            continue
            
        # 计算基础路径的深度，用于控制递归层级
        base_depth = base_path.rstrip(os.sep).count(os.sep)

        try:
            # 使用 os.walk 进行递归扫描
            for root, dirs, files in os.walk(base_path, topdown=True):
                # 过滤目录：排除隐藏目录和系统目录
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in exclude_dirs]
                
                # 深度控制：超过 3 层子目录停止递归 (防止扫描太深)
                current_depth = root.rstrip(os.sep).count(os.sep)
                if current_depth - base_depth > 3:
                    dirs[:] = [] 
                    continue

                for name in files:
                    if name.lower().endswith(extensions):
                        try:
                            # 获取真实路径
                            full_path = os.path.join(root, name)
                            real_path = os.path.realpath(full_path)
                            
                            if real_path in seen_paths:
                                continue
                            
                            seen_paths.add(real_path)
                            
                            stat = os.stat(real_path)
                            found_files.append({
                                "name": name,
                                "path": real_path,
                                "mtime": stat.st_mtime,
                                "size": stat.st_size
                            })
                        except Exception:
                            continue
        except PermissionError:
            continue
        except Exception:
            pass
    
    # 按修改时间倒序
    found_files.sort(key=lambda x: x['mtime'], reverse=True)
    return found_files[:30] # 返回最新的30个文件

def scan_local_videos():
    return _scan_files(('.mp4', '.mkv', '.avi', '.flv', '.mov', '.ts', '.webm'))

def scan_local_audio():
    return _scan_files(('.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg', '.wma'))

def scan_local_images():
    return _scan_files(('.jpg', '.jpeg', '.png', '.bmp', '.webp', '.gif'))

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
    
    # 简单的存储权限检查
    storage_access = "✅ 正常" if os.access("/sdcard", os.R_OK) else "❌ 无权限 (请运行 termux-setup-storage)"

    return (
        f"🖥 **服务器环境报告**\n\n"
        f"🌐 **局域网IP**: `{local_ip}`\n\n"
        f"📂 **存储访问**: {storage_access}\n\n"
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
