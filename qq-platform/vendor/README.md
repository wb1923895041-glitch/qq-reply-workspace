# WeChatAgent 社交引擎来源

此目录中的 22 个源文件来自 WeChatAgent 0.4.1 发布安装包，原始 SHA-256 均匹配该安装包 `deployment.json` 的 `sourceHashes`。源码及原许可来自 <https://github.com/sourcepro5/WeChatAgent>；完整上游许可见 `../UPSTREAM-LICENSE.txt`。

本副本只对 `components/qq-bridge/src/core/social-engine.js` 增加一处 QQ 演练分支：处理 `delivered: preview` 时不把模拟回复记为已发送。其他文件保持原样。QQ 身份、适配和连接隔离逻辑位于本目录之外的 `social-service.js`。
