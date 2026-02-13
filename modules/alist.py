import psutil
import subprocess
import os
import signal
import asyncio
import json
import requests
from .config import load_config, save_config

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

def get_auth_token():
    """获取 Alist Token，如果未配置则尝试通过账号密码登录获取"""
    config = load_config()
    token = config.get('alist_token', '')
    
    # 如果已有 Token，直接返回
    if token:
        return token
        
    # 尝试自动登录
    user = config.get('alist_user')
    pwd = config.get('alist_password')
    host = config.get('alist_host', "http://127.0.0.1:5244")
    
    if user and pwd:
        try:
            login_url = f"{host}/api/auth/login"
            resp = requests.post(login_url, json={"username": user, "password": pwd}, timeout=5)
            data = resp.json()
            if data.get("code") == 200:
                new_token = data.get("data", {}).get("token")
                if new_token:
                    # 登录成功，保存 Token 到配置文件，避免重复登录
                    save_config({'alist_token': new_token})
                    return new_token
        except Exception as e:
            print(f"Alist 自动登录失败: {e}")
            pass
            
    return ""

async def mount_local_storage():
    """调用 API 挂载本机存储"""
    config = load_config()
    token = get_auth_token() # 使用自动获取逻辑
    
    if not token:
        return False, "未获取到 Alist Token，且自动登录失败 (请检查 .env 中的用户/密码)"
    
    base_url = config.get('alist_host', "http://127.0.0.1:5244")
    api_url = f"{base_url}/api/admin/storage/create"
    
    headers = {
        "User-Agent": "TermuxBot",
        "Content-Type": "application/json",
        "Authorization": token
    }
    
    # 挂载 /sdcard
    payload = {
        "mount_path": "/本机存储",
        "driver": "Local",
        "cache_expiration": 30,
        "status": "work",
        "addition": "{\"root_folder_path\":\"/sdcard\",\"thumbnail\":true,\"thumb_cache_folder\":\"\",\"show_hidden\":true,\"mkdir_perm\":\"777\"}",
        "remark": "Auto Mounted by TermuxBot",
        "order": 0,
        "web_proxy": False,
        "webdav_policy": "302_on_lan"
    }

    try:
        resp = requests.post(api_url, json=payload, headers=headers, timeout=5)
        data = resp.json()
        if data.get("code") == 200:
            return True, "✅ 挂载成功！请刷新列表查看 `/本机存储`"
        else:
            return False, f"挂载失败: {data.get('message')}"
    except Exception as e:
        return False, str(e)

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

def alist_list_files(path="/", page=1, per_page=0):
    """
    调用 Alist API 获取文件列表
    返回: (success, data_list/error_msg)
    """
    config = load_config()
    token = get_auth_token() # 使用自动获取逻辑
    base_url = config.get('alist_host', "http://127.0.0.1:5244")
    
    api_url = f"{base_url}/api/fs/list"
    headers = {
        "User-Agent": "TermuxBot",
        "Content-Type": "application/json"
    }
    if token:
        headers["Authorization"] = token

    payload = {
        "path": path,
        "password": "",
        "page": page,
        "per_page": per_page,
        "refresh": False
    }

    try:
        resp = requests.post(api_url, json=payload, headers=headers, timeout=5)
        data = resp.json()
        
        if data.get("code") == 200:
            return True, data.get("data", {}).get("content", [])
        else:
            return False, data.get("message", "Unknown API Error")
    except Exception as e:
        return False, str(e)