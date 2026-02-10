import psutil
import subprocess
import os
import signal
import asyncio
import json

def get_alist_pid():
    """查找 alist 进程 PID"""
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if 'alist' in proc.info['name']:
                return proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None

def check_alist_version():
    """检查 Alist 版本"""
    try:
        output = subprocess.check_output(["alist", "version"], stderr=subprocess.STDOUT, text=True)
        for line in output.splitlines():
            if "Version" in line:
                return line.split(":")[-1].strip()
        return "Unknown"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

async def fix_alist_config():
    """尝试修复 Alist 配置文件并重启"""
    # 1. 停止 Alist
    pid = get_alist_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(10): # 等待 5 秒
                await asyncio.sleep(0.5)
                if not get_alist_pid():
                    break
            if get_alist_pid():
                os.kill(pid, signal.SIGKILL)
        except:
            pass
    
    # 2. 查找并修改配置
    log_msg = "🛠 **执行修复操作...**\n"
    search_paths = [
        os.path.join(os.getcwd(), "data", "config.json"),
        os.path.expanduser("~/.alist/data/config.json"),
    ]
    
    found_config = False
    for p in search_paths:
        if os.path.exists(p):
            found_config = True
            try:
                with open(p, 'r') as f:
                    config_data = json.load(f)
                
                changed = False
                # 确保 scheme 存在
                if 'scheme' not in config_data:
                    config_data['scheme'] = {}
                    changed = True
                
                # 强制修改 scheme.address
                if isinstance(config_data['scheme'], dict):
                    if config_data['scheme'].get('address') != '0.0.0.0':
                        config_data['scheme']['address'] = '0.0.0.0'
                        changed = True
                
                if changed:
                    with open(p, 'w') as f:
                        json.dump(config_data, f, indent=4)
                    log_msg += f"✅ 已修改配置文件: `{p}`\n"
                else:
                    log_msg += f"👌 配置无需修改: `{p}`\n"
                    
            except Exception as e:
                log_msg += f"❌ 配置文件错误 `{p}`: {str(e)}\n"
    
    if not found_config:
            log_msg += "⚠️ 未找到配置文件，尝试启动以生成默认配置。\n"

    # 3. 重启 Alist
    subprocess.Popen(["alist", "server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await asyncio.sleep(3)
    
    new_pid = get_alist_pid()
    status = "✅ 重启成功" if new_pid else "❌ 重启失败"
    
    return log_msg, status, new_pid
