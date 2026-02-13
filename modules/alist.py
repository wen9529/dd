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

def get_alist_admin_password():
    """尝试通过 alist admin 命令获取密码 (适配不同版本输出)"""
    try:
        # 运行 alist admin
        # 常见输出: "admin: xxxxx" 或 "username: admin\npassword: xxxxx"
        output = subprocess.check_output(["alist", "admin"], text=True, stderr=subprocess.STDOUT).strip()
        
        password = ""
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith("password:"):
                password = line.split("password:")[-1].strip()
                break
            elif line.startswith("admin:"):
                password = line.split("admin:")[-1].strip()
                break
        
        # 如果没匹配到，尝试取最后一行（旧版本行为）
        if not password and lines:
            # 过滤掉可能的日志行 [INFO] 等
            valid_lines = [l for l in lines if not l.startswith('[') and len(l) > 5]
            if valid_lines:
                password = valid_lines[-1].strip()
                
        return password
    except Exception as e:
        print(f"Failed to get alist admin password: {e}")
        return None

def get_auth_token():
    """获取 Alist Token，如果未配置则尝试通过账号密码登录获取"""
    config = load_config()
    token = config.get('alist_token', '')
    
    # 如果已有 Token，直接返回
    if token:
        return token
        
    # 尝试自动登录
    user = config.get('alist_user', 'admin')
    pwd = config.get('alist_password')
    host = config.get('alist_host', "http://127.0.0.1:5244")
    
    # 1. 如果没有密码，尝试从 CLI 获取
    if not pwd:
        print("Bot: 未配置 Alist 密码，尝试自动获取...")
        pwd = get_alist_admin_password()
        if pwd:
            print(f"Bot: 自动获取密码成功，已保存。")
            save_config({'alist_password': pwd})
        else:
            print("Bot: 自动获取密码失败，请手动配置。")

    # 2. 尝试登录获取 Token
    if user and pwd:
        try:
            login_url = f"{host}/api/auth/login"
            resp = requests.post(login_url, json={"username": user, "password": pwd}, timeout=5)
            data = resp.json()
            if data.get("code") == 200:
                new_token = data.get("data", {}).get("token")
                if new_token:
                    print("Bot: Alist 登录成功，Token 已更新。")
                    # 登录成功，保存 Token 到配置文件，避免重复登录
                    save_config({'alist_token': new_token})
                    return new_token
            else:
                print(f"Bot: Alist 登录失败: {data.get('message')}")
        except Exception as e:
            print(f"Bot: Alist 登录请求异常: {e}")
            pass
            
    return ""

def resolve_alist_path(path):
    """
    通过 API 获取文件的真实下载链接
    包含 401 自动重试逻辑 (Token 过期自动刷新)
    """
    config = load_config()
    base_url = config.get('alist_host', "http://127.0.0.1:5244")
    api_url = f"{base_url}/api/fs/get"
    
    # 定义请求函数
    def _do_request(_token):
        headers = {
            "User-Agent": "TermuxBot",
            "Content-Type": "application/json"
        }
        if _token:
            headers["Authorization"] = _token
            
        payload = {
            "path": path,
            "password": ""
        }
        return requests.post(api_url, json=payload, headers=headers, timeout=8)

    # 第一次尝试
    token = get_auth_token()
    try:
        resp = _do_request(token)
        data = resp.json()
        
        # 处理 401 Unauthorized (Token 失效)
        if resp.status_code == 401 or data.get("code") == 401:
            print("Bot: Alist Token 已失效，尝试重新登录...")
            save_config({'alist_token': ''}) # 清除旧 Token
            token = get_auth_token() # 触发重新获取
            if token:
                resp = _do_request(token) # 重试
                data = resp.json()

        if data.get("code") == 200:
            return data.get("data", {}).get("raw_url")
        else:
            print(f"Resolve Path Error: {data.get('message')}")
    except Exception as e:
        print(f"Resolve Path Exception: {e}")
        
    return None

async def mount_local_storage():
    """调用 API 挂载本机存储"""
    config = load_config()
    
    # 确保 Alist 正在运行
    if not get_alist_pid():
        return False, "Alist 未运行，请先启动服务"

    token = get_auth_token() # 使用自动获取逻辑
    
    if not token:
        return False, "未获取到 Alist Token，且自动获取密码失败。\n请尝试手动运行 `alist admin` 查看密码，并在 Bot 设置中配置。"
    
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
        elif "repect" in str(data.get("message")): # 兼容拼写错误 'repect' vs 'repeat'
            return True, "✅ 存储已存在，无需重复挂载"
        elif "duplicate" in str(data.get("message")):
            return True, "✅ 存储已存在，无需重复挂载"
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
    # Alist V3 在 Termux 下通常在当前目录 data/config.json 或 ~/.alist/data/config.json
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
                
                scheme = config_data['scheme']

                # 1. 强制监听所有接口 0.0.0.0 (解决 Cloudflare 无法连接 127.0.0.1 的部分情况)
                if scheme.get('address') != '0.0.0.0':
                    scheme['address'] = '0.0.0.0'
                    changed = True
                    log_msg += "  - 修正监听地址为 0.0.0.0\n"

                # 2. 强制端口为 5244 (标准端口)
                if int(scheme.get('http_port', 0)) != 5244:
                    scheme['http_port'] = 5244
                    changed = True
                    log_msg += "  - 修正端口为 5244\n"
                
                # 3. 强制关闭强制 HTTPS (避免内网访问 SSL 错误)
                if scheme.get('force_https') is True:
                    scheme['force_https'] = False
                    changed = True
                    log_msg += "  - 关闭强制 HTTPS\n"

                if changed:
                    with open(p, 'w') as f:
                        json.dump(config_data, f, indent=4)
                    log_msg += f"✅ 已更新配置文件: `{p}`\n"
                else:
                    log_msg += f"👌 配置正常: `{p}`\n"
                    
            except Exception as e:
                log_msg += f"❌ 配置文件解析错误 `{p}`: {str(e)}\n"
    
    if not found_config:
            log_msg += "⚠️ 未找到配置文件，Alist 将使用默认设置启动 (请稍后再次执行修复以确认)。\n"

    # 清除旧的错误 Token，强迫下次重新获取
    save_config({'alist_token': ''})
    log_msg += "🔄 已重置本地缓存的 Alist Token\n"

    # 3. 重启 Alist
    # 使用 pm2 启动以保持一致性
    subprocess.run("pm2 restart termux-alist", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # 备用方案：如果 pm2 没起来
    if not get_alist_pid():
        subprocess.Popen(["alist", "server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    await asyncio.sleep(4)
    
    new_pid = get_alist_pid()
    status = "✅ 重启成功 (端口 5244)" if new_pid else "❌ 重启失败"
    
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
