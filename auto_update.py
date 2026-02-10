import time
import subprocess
import logging
import sys

# 配置日志
logging.basicConfig(
    format='%(asctime)s - [Updater] - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)

def run_command(command, check=True):
    """运行系统命令"""
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            check=check, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {command}\nError: {e.stderr}")
        raise

def check_and_update():
    try:
        # 1. 获取远程最新状态
        subprocess.run("git fetch", shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # 2. 对比本地 HEAD 和远程上游分支的 Hash
        local_hash = run_command("git rev-parse HEAD")
        remote_hash = run_command("git rev-parse @{u}")

        if local_hash != remote_hash:
            logging.info("♻️ 检测到新版本！准备更新...")

            # 3. 保护本地修改 (Stash)
            has_changes = run_command("git status --porcelain")
            stashed = False
            if has_changes:
                logging.info("💾 暂存本地修改 (Token/配置)...")
                run_command("git stash")
                stashed = True

            # 4. 拉取更新
            run_command("git pull")
            logging.info("✅ 代码拉取成功")

            # 5. 恢复本地修改
            if stashed:
                try:
                    run_command("git stash pop")
                    logging.info("📂 本地配置已恢复")
                except Exception:
                    logging.warning("⚠️ 恢复配置时发生冲突，请手动检查 bot.py")

            # 6. 运行 setup.sh 进行部署
            logging.info("🚀 触发 setup.sh 进行重载...")
            # 注意：setup.sh 内部会重启 bot 进程，但我们不希望 updater 重启自己
            # 所以 setup.sh 需要有逻辑避免重启 updater
            subprocess.run("bash setup.sh", shell=True, check=True)
            logging.info("🎉 更新流程结束，等待下一次检查...")
        else:
            # 这里的日志可以注释掉，避免刷屏，仅在有动作时记录
            # logging.info("暂无更新")
            pass

    except Exception as e:
        logging.error(f"更新检查出错: {e}")

if __name__ == "__main__":
    logging.info("🛡️ 自动更新守护进程已启动 (检查周期: 60秒)")
    while True:
        check_and_update()
        time.sleep(60)
