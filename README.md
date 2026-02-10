# Termux Telegram Bot (Alist + FFmpeg + AutoUpdate)

这是一个 Termux 上的多功能机器人，集成了 **Alist 网盘管理**、**直播推流** 以及 **全自动更新** 功能。

## 🚀 核心功能

1.  **🤖 全自动更新**: 
    *   内置 `termux-updater` 守护进程。
    *   **每分钟** 自动检查 Git 仓库。
    *   发现更新后自动拉取，并智能重启机器人，同时保留你的 Token 配置。
2.  **🗂 Alist 管理**: 一键查看状态、启动停止、获取密码。
3.  **📺 直播推流**: 支持使用 Alist 路径直接推流到 Telegram。
4.  **🛡 进程守护**: 使用 PM2 双进程管理（Bot + Updater）。

## 📥 安装与启动

在 Termux 中执行一次即可：

```bash
bash setup.sh
```

**脚本将会启动两个后台进程：**
1.  `termux-bot`: 你的 Telegram 机器人核心。
2.  `termux-updater`: 自动更新检查器。

## 🎮 使用指南

### 基础命令
*   `/start` - 查看主菜单和 ID。
*   `/alist` - 打开 Alist 管理面板。
*   `/stream <路径> <RTMP地址>` - 开始推流。

### 进程管理 (PM2)
*   **查看状态**: `pm2 list`
*   **查看机器人日志**: `pm2 log termux-bot`
*   **查看更新日志**: `pm2 log termux-updater` (可以看到是否有新版本被检测到)
*   **停止所有**: `pm2 stop all`

## ⚠️ 注意事项
*   **Token 保护**: 自动更新脚本使用了 `git stash` 技术，这意味着如果你修改了 `bot.py` 里的 Token，更新时会自动暂存并恢复，**不会被覆盖**。
*   **冲突处理**: 如果官方更新了 `bot.py` 的结构，而你也修改了大量代码，可能会产生冲突。此时建议查看 `pm2 log termux-updater` 排查。
