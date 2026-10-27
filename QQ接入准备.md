# QQ 接入准备记录

本机独立运行目录：`output/napcat/NapCat.52230.Shell/`，不会提交到 GitHub。安装输出显示文件被整理到独立目录；准备后原有 QQ 主窗口对应进程仍在。没有对系统其他目录做完整变更审计。

- NapCat 官方发布 `v4.18.41` 的 `NapCat.Shell.Windows.OneKey.zip`：已核对 GitHub Release 提供的 SHA-256。
- 安装器从腾讯地址获取 QQ 9.9.33-52230 并解压在独立目录；下载的 QQ 安装包和独立目录中的 QQ 可执行文件的 Windows 数字签名均有效，签名主体为 Tencent Technology (Shenzhen) Company Limited。
- 安装器下载的 `NapCat.Shell.zip` SHA-256 与官方 `v4.18.41` Release 的资产摘要一致；解压所得 685 个文件逐一与 ZIP 内容的 SHA-256 比对一致。
- 尚未登录 QQ、配置 NapCat WebUI/OneBot 或进行真实群聊收发。安装完成不能视为机器人已连接。

可双击本项目的 `启动QQ机器人.cmd` 启动独立运行时，按其界面提示登录。完成登录后，在 NapCat 的 OneBot 连接中添加 **WS 反向客户端**，连接 URL 为 `ws://127.0.0.1:18766/onebot`，消息格式选择 Array，Token 与本工作台“设置连接令牌.cmd”一致。先启动工作台服务并保持演练模式，再检查 OneBot 连接；机器人 WebUI 的密码与 OneBot Token 是不同凭据。

NapCat 官方说明：<https://napneko.github.io/guide/boot/Shell>；反向 WebSocket 设置：<https://napneko.github.io/NapCatQQ-Desktop/docs/connections/>。
