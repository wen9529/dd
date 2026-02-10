# Termux Telegram Bot (Pure Python)

这是一个专为 Termux 设计的 Telegram 机器人，已移除所有 Web 界面和 AI 功能，仅保留核心 Python 逻辑。

## 🚀 极速启动 (一键运行)

在 Termux 中拉取代码进入目录后，**只需执行这一条命令**：

```bash
bash setup.sh
```

这条命令会自动完成以下所有操作：
1. 安装 Python 环境
2. 安装所需依赖 (`python-telegram-bot`)
3. 自动赋予脚本执行权限
4. 启动机器人

## 🛠 手动维护

如果环境已安装好，后续想手动启动，可以使用：

```bash
python bot.py
```

## ⚠️ 注意事项
`bot.py` 中已包含敏感 Token，请勿将此项目源码公开上传到公共仓库。
