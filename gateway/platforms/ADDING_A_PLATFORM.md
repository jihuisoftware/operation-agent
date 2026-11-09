# 桌面运行时与历史平台契约

当前产品只支持 macOS Desktop，不再添加或激活消息平台、公共 API Server、Webhook 或 MS Graph 接入。
`gateway/config.py` 的 `RUNTIME_PLATFORM_VALUES` 只允许 `local`；环境变量和旧配置不能恢复退役入口。

本目录保留的 `base.py`、`event.py`、媒体缓存及部分 API/Webhook 模块仍服务共享执行契约、历史会话和持久化账本，不能按文件名前缀批量删除。
新能力遵循根 `AGENTS.md` 的 CLI + skill / 服务门控 / 插件扩展顺序，不恢复消息适配器工厂。

- Desktop 的私有连接、票据和会话归属继续由 Gateway 运行时负责。
- 共享 RPC 契约见 `gateway/rpc/AGENTS.md`；私有 HTTP API 见 `hermes_cli/web_routers/AGENTS.md`。
- 模型选项解码在 `gateway/session_model_options.py`，不依赖公共 API 适配器。
- 历史 WhatsApp 身份归一化在 `gateway/session_legacy_identity.py`，不会连接或安装桥接进程。
- 清理其他平台模块前，追踪运行时、历史恢复和测试引用；保留持久化平台值与会话标识兼容。
