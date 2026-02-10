# Termux Telegram Bot (Alist + FFmpeg)

这是一个 Termux 上的多功能机器人，集成了 **Alist 网盘管理** 和 **Telegram 直播推流** 功能。

## 🚀 核心功能

1.  **Alist 管理**:
    *   一键查看运行状态
    *   Bot 指令启动/停止服务
    *   直接获取 Admin 密码
2.  **直播推流**:
    *   使用 `ffmpeg` 将 Alist 中的视频文件（直链）推送到 Telegram 视频直播间。
    *   支持后台运行，随时停止。
3.  **进程守护**: 使用 PM2 自动管理，崩溃自启。

## 📥 安装与更新

在 Termux 中执行：

```bash
bash setup.sh
```

脚本会自动安装 `python`, `ffmpeg`, `alist`, `pm2` 等所有环境。

## 🎮 使用指南

### 1. Alist 管理
发送 `/alist` 获取菜单。
*   **启动**: `/alist_start`
*   **获取密码**: `/alist_admin` (用于登录网页后台挂载网盘)
*   *注意: Alist 默认端口为 5244*

### 2. 推流到 Telegram 直播
1.  **准备视频链接**: 从你的 Alist 复制视频的直链 (例如: `http://192.168.1.5:5244/d/电影/test.mp4`).
2.  **获取推流地址**: 
    *   在 Telegram 群组/频道开启“视频聊天(Video Chat)”或“直播(Live Stream)”。
    *   点击“使用其他应用推流(Stream with...)”。
    *   复制 **服务器地址 (Server URL)** 和 **推流密钥 (Stream Key)**。
    *   将它们拼接在一起：`服务器地址/推流密钥` (注意中间可能有斜杠，通常 TG 链接类似 `rtmps://...:443/s/KEY`).
3.  **发送指令**:
    ```text
    /stream <视频链接> <RTMP完整地址>
    ```
4.  **停止推流**:
    ```text
    /stopstream
    ```

## ⚠️ 注意事项
*   推流十分消耗手机电量和 CPU，建议连接电源使用。
*   请确保网络环境良好，否则直播可能会卡顿。
*   Token 和 Owner ID 仍然硬编码在 `bot.py` 中，请注意保护。
