import time
import subprocess
import logging
import sys
from modules.config import load_config

# 配置日志
logging.basicConfig(
    format='%(asctime)s - [Updater] - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)

def configure_git_auth():
    """如果存在 Github PAT，配置远程 URL 以支持私有仓库更新"""
    config = load_config()
    pat = config.get('github_pat')
    owner = config.get('github_owner')
    repo = config.get('github_repo')
    
    if pat and owner and repo:
        try:
            # 构建带 Token 的 URL
            # 格式: https://<TOKEN>@github.com/<OWNER>/<REPO>.git
            auth_url = f"https://{pat}@github.com/{owner}/{repo}.git"
            
            # 更新 remote url
            subprocess.run(f"git remote set-url origin {auth_url}", shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logging.info("🔐 已配置 Git 鉴权信息 (使用 PAT)")
        except Exception as e:
            logging.error(f"配置 Git 鉴权失败: {e}")

def check_and_update():
    try:
        # 1. 获取远程最新状态
        subprocess.run("git fetch", shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # 2. 对比本地 HEAD 和远程上游分支的 Hash
        local_hash = subprocess.check_output("git rev-parse HEAD", shell=True).strip()
        remote_hash = subprocess.check_output("git rev-parse @{u}", shell=True).strip()

        if local_hash != remote_hash:
            logging.info("♻️ 检测到新版本！准备更新...")
            
            # 直接调用 setup.sh 进行更新和重启
            # setup.sh 内部处理了 git stash, pull, pm2 restart
            subprocess.run("bash setup.sh", shell=True, check=True)
            
            logging.info("🎉 更新流程结束，等待下一次检查...")
        else:
            pass # 暂无更新

    except Exception as e:
        logging.error(f"更新检查出错: {e}")
        # 如果出错，等待较长时间再试，防止死循环刷日志
        time.sleep(60)

if __name__ == "__main__":
    logging.info("🛡️ 自动更新守护进程已启动 (检查周期: 60秒)")
    
    # 启动时配置鉴权
    configure_git_auth()
    
    # 启动时先尝试拉取一次，保证最新
    try:
        subprocess.run("git pull", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass
        
    while True:
        check_and_update()
        time.sleep(60)
