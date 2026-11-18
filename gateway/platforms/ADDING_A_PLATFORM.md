# 平台扩展边界与历史契约

本文件保留原路径供开发指引引用，当前用途是说明平台边界，**不是上游通用消息适配器的新增教程**。
产品范围以根 [AGENTS.md](../../AGENTS.md) 和 [operations-profile.json](../../hermes_cli/data/operations-profile.json) 为准。

## 三类“平台”分别处理

| 类型 | 当前状态 | 扩展位置 |
| --- | --- | --- |
| 桌面操作系统 | macOS；Windows x64 已恢复源码准入及构建链路，仍待原生验收 | Desktop、安装器、打包脚本及 `hermes_platform` |
| Gateway 消息接入 | 当前运行时只激活 `local`；消息平台、公共 API Server、Webhook、MS Graph 接入已退役 | 本目录保留共享契约，不新增启用入口 |
| 运营网站 | 自动网页发布目前重点支持小红书；其他网站的登录入口不代表支持完整运营流程 | `plugins/operations/` 与 Desktop 运营插件的网页执行层 |

Windows 的构建、安装、签名与升级状态见 [Windows 开发说明](../../docs/windows-development.md)。
恢复 Windows 不需要向 Gateway 添加一个 `windows` 消息平台。

## Gateway 的实际准入与通信

- [config.py](../config.py) 的 `RUNTIME_PLATFORM_VALUES` 只允许 `local`；配置加载时会过滤其他平台。
- [run_adapters.py](../run_adapters.py) 使用平台注册表实例化适配器，已没有旧的外部内置适配器工厂。只新增适配器文件、注册插件或修改环境变量，不能绕过产品的运行时准入范围。
- Desktop 通过 `hermes gateway ensure --json` 连接同一后台，私有控制通道负责票据，HTTP/WebSocket 负责业务请求和事件。公共消息接入退役不影响这些私有接口。
- 会话准入、持久队列与执行归属在 `session_*.py`；辅助 RPC 在 `rpc/`，传输在 `transport/`，协议模型在 `contracts/`。详见 [Gateway 分层说明](../../docs/gateway-rpc.md)。
- UI 或模型工具被禁用，不代表所有相关后台模块都停止运行。例如 hosted-room 的服务初始化路径仍保留；判断是否运行需追踪启动和门控代码，不能只看桌面入口。

## 增加运营网站能力

新运营网站应沿用插件的账号、命令队列和网页执行契约，不把网站名称加入 Gateway 消息平台枚举。
入口可从 [账号页面](../../apps/desktop/src/plugins/operations/platform-pages.tsx)、
[网页执行器](../../apps/desktop/src/plugins/operations/browser.ts) 和 [业务代码地图](../../docs/code-map.md) 查找。

接入时需要明确支持哪些动作，并实现对应的登录识别、提交前检查、结果核对、超时与取消处理。
仅支持登录或读取的网站不能被展示为已支持自动发布；结果未知的提交只核对，不自动重发。
配置、凭据、请求和回执均保留连接、Profile、业务、主题及账号归属。

新能力遵循根开发指引的 CLI + skill、服务门控或插件扩展原则，不新增没有实际消费者的核心工具。
若未来明确决定恢复消息平台，应另行制定准入、配置、授权、依赖和兼容方案；本文件不授权恢复退役入口。

## 历史代码与验证

- `base.py`、`event.py`、媒体缓存及部分 API/Webhook 模块仍被共享执行、历史会话和持久化账本使用，不能按名称批量删除。
- 模型选项解码位于 [session_model_options.py](../session_model_options.py)；历史 WhatsApp 身份归一化位于 [session_legacy_identity.py](../session_legacy_identity.py)，后者不恢复消息桥接。
- 清理前追踪调用方、恢复路径与测试，保留持久化平台值及会话标识兼容；不要通过改写历史记录假装旧平台从未存在。
- 按改动范围验证 [RPC](../rpc/AGENTS.md)、[传输](../transport/AGENTS.md)、[协议](../contracts/AGENTS.md) 或 [私有 HTTP API](../../hermes_cli/web_routers/AGENTS.md)。Python 测试使用 `scripts/run_tests.sh`。
- 网页动作先使用隔离数据与模拟平台验证；真实验收默认只读。Windows 行为须在 Windows 验收，不能用 macOS 结果替代。
