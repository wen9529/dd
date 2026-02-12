import subprocess
import psutil
import socket
import os
import time
import asyncio
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

def get_disk_usage():
    """获取磁盘使用率"""
    try:
        # 检查 /sdcard 或 内部存储
        path = "/sdcard" if os.path.exists("/sdcard") else "/"
        usage = psutil.disk_usage(path)
        return f"{format_size(usage.used)} / {format_size(usage.total)} ({usage.percent}%)"
    except:
        return "未知"
        
def get_thermal_status():
    """尝试获取设备温度 (Termux 特性)"""
    try:
        # 尝试通过 termux-battery-status 获取
        output = subprocess.check_output(["termux-battery-status"], text=True, stderr=subprocess.DEVNULL)
        import json
        data = json.loads(output)
        temp = data.get("temperature", 0)
        return f"{temp:.1f}°C"
    except:
        # 尝试读取系统文件
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp = int(f.read().strip()) / 1000
                return f"{temp:.1f}°C"
        except:
            return "N/A"

def get_system_uptime():
    """获取系统运行时间"""
    try:
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"{int(days)}天 {int(hours)}小时 {int(minutes)}分"
    except:
        return "未知"

async def run_shell_command(cmd):
    """异步执行 Shell 命令"""
    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        res = ""
        if stdout: res += f"{stdout.decode().strip()}\n"
        if stderr: res += f"ERROR:\n{stderr.decode().strip()}"
        
        if not res.strip(): res = "✅ 执行成功 (无输出)"
        return res
    except Exception as e:
        return f"❌ 执行出错: {str(e)}"

def run_speedtest_sync():
    """同步运行 Speedtest (将在线程中调用)"""
    try:
        import speedtest
        st = speedtest.Speedtest()
        st.get_best_server()
        download = st.download() / 1024 / 1024 # Mbps
        upload = st.upload() / 1024 / 1024 # Mbps
        ping = st.results.ping
        return True, f"⬇️ 下载: {download:.2f} Mbps\n⬆️ 上传: {upload:.2f} Mbps\n📶 延迟: {ping:.0f} ms"
    except ImportError:
        return False, "❌ 未安装 speedtest-cli 库"
    except Exception as e:
        return False, f"❌ 测试失败: {str(e)}"

def _scan_files_sync(extensions, extra_paths=[]):
    """
    优化的同步文件扫描
    使用 os.scandir 替代 os.walk，速度更快
    """
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
        
        # 3. 根目录
        "/sdcard",
        
        # 4. Termux 内部
        os.getcwd()
    ] + extra_paths
    
    found_files = []
    seen_paths = set() 
    exclude_dirs = {'Android', 'LOST.DIR', 'System Volume Information', 'MIUI', 'data', 'obb', '.git', '__pycache__', 'cache', 'log'}

    for base_path in search_paths:
        if not os.path.exists(base_path): continue
            
        base_depth = base_path.rstrip(os.sep).count(os.sep)

        try:
            for root, dirs, files in os.walk(base_path, topdown=True):
                # 过滤目录
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in exclude_dirs]
                
                # 严格控制深度：只向下扫 3 层
                current_depth = root.rstrip(os.sep).count(os.sep)
                if current_depth - base_depth > 3:
                    dirs[:] = []
                    continue

                for name in files:
                    if name.lower().endswith(extensions):
                        try:
                            full_path = os.path.join(root, name)
                            # 避免重复
                            if full_path in seen_paths: continue
                            
                            stat = os.stat(full_path)
                            # 过滤掉小于 100KB 的文件 (通常是缓存或缩略图)
                            if stat.st_size < 102400: continue
                            
                            seen_paths.add(full_path)
                            found_files.append({
                                "name": name,
                                "path": full_path,
                                "mtime": stat.st_mtime,
                                "size": stat.st_size
                            })
                        except:
                            continue
        except:
            pass
    
    # 按修改时间倒序，取前 40 个
    found_files.sort(key=lambda x: x['mtime'], reverse=True)
    return found_files[:40]

def scan_local_videos():
    return _scan_files_sync(('.mp4', '.mkv', '.avi', '.flv', '.mov', '.ts', '.webm'))

def scan_local_audio():
    return _scan_files_sync(('.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg', '.wma'))

def scan_local_images():
    return _scan_files_sync(('.jpg', '.jpeg', '.png', '.bmp', '.webp', '.gif'))

def get_env_report():
    """生成环境报告文本"""
    ffmpeg_ver = check_program_version("ffmpeg")
    alist_ver = check_alist_version()
    alist_pid = get_alist_pid()
    stream_active = get_stream_status()
    local_ip = get_local_ip()
    temp = get_thermal_status()
    
    cpu_usage = psutil.cpu_percent(interval=None)
    mem_info = psutil.virtual_memory()
    mem_usage = f"{mem_info.used / 1024 / 1024:.0f}MB / {mem_info.total / 1024 / 1024:.0f}MB"
    disk_usage = get_disk_usage()
    uptime = get_system_uptime()
    
    storage_access = "✅ 正常" if os.access("/sdcard", os.R_OK) else "❌ 无权限"

    return (
        f"🖥 **Termux 状态报告**\n\n"
        f"🌐 **IP**: `{local_ip}`\n"
        f"⏱ **运行**: {uptime}\n"
        f"💾 **存储**: {disk_usage}\n"
        f"🌡 **温度**: {temp}\n\n"
        f"🎥 **FFmpeg**:\n"
        f"• 状态: {'✅ ' + ffmpeg_ver if ffmpeg_ver else '❌ 未安装'}\n"
        f"• 任务: {'🔴 推流中' if stream_active else '⚪ 空闲'}\n\n"
        f"🗂 **Alist**:\n"
        f"• 状态: {'✅ ' + alist_ver if alist_ver else '❌ 未安装'}\n"
        f"• 进程: {'🟢 运行中' if alist_pid else '🔴 已停止'}\n\n"
        f"⚙️ **资源**: CPU {cpu_usage}% | RAM {mem_usage}"
    )
