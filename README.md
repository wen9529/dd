# Termux Telegram Bot (Python + PM2)

这是一个专为 Termux 环境优化的 Telegram 机器人项目。
特点：**纯 Python 核心** + **PM2 进程守护** + **一键自动更新部署**。

## ✨ 核心特性

*   **智能安装**: 自动检测系统依赖 (Python, Node.js, Git)，已安装则跳过，绝不重复下载。
*   **进程守护**: 使用 PM2 管理机器人，崩溃自动重启，后台稳定运行。
*   **自动更新**: 每次运行脚本自动拉取最新代码 (Git Pull)。
*   **一键启动**: 只需要运行一个脚本即可完成所有工作。

## 🚀 极速启动

在 Termux 中拉取代码进入目录后，执行：

```bash
bash setup.sh
```

**脚本将会自动执行：**
1. 🔄 检查 Git 仓库更新
2. 📦 检查并补全 Python/Node.js/PM2 环境
3. 🐍 安装 Python 依赖库
4. 🤖 使用 PM2 在后台启动/重启机器人
5. 📄 展示运行日志预览

## 🛠 管理命令 (PM2)

机器人启动后会在后台运行，你可以使用以下命令进行管理：

*   **查看实时日志**:
    ```bash
    pm2 log termux-bot
    ```
*   **停止机器人**:
    ```bash
    pm2 stop termux-bot
    ```
*   **重启机器人**:
    ```bash
    pm2 restart termux-bot
    ```
*   **查看状态列表**:
    ```bash
    pm2 list
    ```

## ⚠️ 注意事项

*   **Token 安全**: `bot.py` 中包含 Token，请勿泄露。
*   **完全卸载**: 如果你想彻底停止并删除进程，使用 `pm2 delete termux-bot`。
