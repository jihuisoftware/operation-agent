# hermes_cli 职责与阅读导航

`hermes_cli` 是历史包名。当前目录同时提供管理命令、非交互客户端、配置与认证服务、Gateway 生命周期管理和 Desktop 私有 HTTP API；它不是一个单独的后台进程，也不等于终端聊天界面。

开发约束见 [AGENTS.md](AGENTS.md)，产品范围以[根开发指引](../AGENTS.md)和[运营产品配置](data/operations-profile.json)为准。本页是代码导航，不改变功能开关。

## 当前入口与产品边界

- 用户聊天使用 Desktop。`main.py::cmd_chat` 拒绝普通交互终端聊天，保留单次请求、批处理和结构化输出等执行路径。
- Desktop 通过 `hermes gateway ensure --json` 发现或启动后台。关闭窗口不等于停止 Gateway，也不会为每个窗口另起一套会话权威。
- `web_server*` 和 `web_routers/` 是仍被桌面使用的后台接口；旧 `web/` SPA 和 `ui-tui/` 不再提供。
- macOS 是现有桌面目标；Windows x64 已恢复源码准入与构建链路，原生验收状态见 [Windows 开发说明](../docs/windows-development.md)。保留的 Linux 服务管理代码不等于当前支持 Linux 桌面分发。
- Bot Mode、Radio、消息平台和公共 API/Webhook 接入已退役；delegation 与 MCP 仍关闭。Kanban 已恢复，逐看板自动执行默认关闭。
- 文件存在、模块被导入、后台服务被初始化、能力向用户开放是不同状态。历史名称和协议值不足以判断代码能否删除。

## 职责地图

| 职责 | 优先入口 | 边界 |
| --- | --- | --- |
| 命令解析与分派 | [main.py](main.py)、[subcommands/](subcommands/) | `pyproject.toml` 的 `hermes` 入口指向 `hermes_cli.main:main`；解析命令后委派给对应模块 |
| Gateway 管理 | [gateway.py](gateway.py)、[gateway_runtime.py](gateway_runtime.py)、[gateway_client.py](gateway_client.py) | 进程发现、启停、票据与客户端通信；后台主生命周期位于 `gateway/` |
| 配置 | [config.py](config.py)、[config_defaults.py](config_defaults.py)、[config_effective.py](config_effective.py) | 合并、读写、校验、迁移及产品范围；不是模型执行循环 |
| Profile | [profiles.py](profiles.py) 及 `profiles*`、`profile_*` | 管理身份与目录；多个 Profile 可以由同一 Gateway 服务 |
| 模型与凭据 | [models.py](models.py)、[auth.py](auth.py)、`model_*`、`auth*` | 服务商与模型选择、认证和凭据处理；实际推理位于 `agent/` |
| Desktop HTTP | [web_server.py](web_server.py)、`web_server_*`、[web_routers/](web_routers/README.md) | 私有路由、鉴权、Profile 作用域；不是公共 API Server 适配器 |
| 斜杠命令 | [commands.py](commands.py)、[slash_exec.py](slash_exec.py) | 统一注册信息和执行入口，Desktop 再按产品范围与展示规则筛选 |
| 插件 | [plugins.py](plugins.py)、`plugins_*`、`plugin_*` | 发现、安装、验证和隔离；插件业务实现在各插件目录 |
| 更新与恢复 | [update_cmd.py](update_cmd.py)、`update_*`、[update_handoff.py](update_handoff.py) | 更新事务、回滚、重启及跨版本兼容；不要按旧命名删恢复入口 |
| Kanban | [kanban.py](kanban.py)、[kanban_execution.py](kanban_execution.py)、[kanban_worker_client.py](kanban_worker_client.py) | 看板存储/调度和任务客户端；Worker 向所属 Profile 的 Gateway 提交执行 |
| 本地模型运行环境 | [local_runtime/](local_runtime/) | 硬件、端点、模型运行能力及进程相关辅助功能 |
| 可观测性 | [observability/](observability/) | 日志、运行记录及相关集成；存在集成代码不代表已启用遥测 |
| CLI 共享与兼容实现 | [../cli.py](../cli.py)、`cli_*`、`stream_json*`、`gateway_chat*` | 单次请求、命令、输出与共享客户端；保留类名不恢复交互终端产品 |

这些分组是职责导航，不是独立部署单元。同一模块可能在命令进程、Gateway 或受管 Worker 中被导入。

## 三条常用调用链

```text
后台启动：
hermes gateway run
  → main.py / gateway.py
  → gateway/run.py / run_bootstrap.py
  → GatewayRunner、会话权威、监听器与调度

桌面设置和插件 HTTP：
Desktop → Electron 私有 HTTP 桥接
  → gateway/run_api.py
  → hermes_cli.web_server / web_routers / 插件私有 router
  → 对应服务和当前 Profile 的数据

桌面聊天：
Desktop → /api/ws → gateway/transport/ws.py
  → gateway/session_controls.py → SessionAuthority
  → 按冻结策略选择执行路径 → AIAgent.run_conversation()
```

聊天不会先绕到旧终端界面执行。它仍会使用本目录的配置、模型、凭据等共享服务。完整后台分层见 [Gateway 通信与 RPC](../docs/gateway-rpc.md)。

## 配置与状态的归属

- `load_config()` 合并默认配置；`load_user_config_effective()` 是不注入完整默认值的有效配置读取。不同读取器不是可互换的别名。
- `data/operations-profile.json` 表达产品范围；它不等于用户配置文件，也不能用保留的上游配置键推断某能力已开放。
- 用户设置和密钥通过所属 Profile 的路径及作用域读取，不固定到默认目录。业务代码不借用进程启动 Profile 的环境变量。
- `state/` 负责会话、消息与运行账本；运营插件负责业务/主题数据；Kanban 在同一 Hermes 根目录内共享看板是其既有设计，不应类推到会话与凭据。

## 修改与清理时的顺序

先用 [代码地图](../docs/code-map.md) 定位功能，再找入口、调用方和测试。已有门面与兄弟模块的晚导入/绑定规则见本目录开发指引；不要把拆文件变成另一份共享状态。

新增运营业务放在运营插件中。通用 HTTP 接口复用既有认证和 Profile 路由；模型循环改动进入 `agent/`；会话权威与队列改动进入 `gateway/session_*`。不要因为当前文件在 `hermes_cli` 下，就把所有新行为继续堆进 `main.py` 或 `gateway.py`。

清理 `cli_tui_*`、旧协议处理器或更新模块前，分别核对运行时调用、历史数据恢复和旧版本升级契约。没有用户入口，不代表没有内部消费者；迁移内部符号时同步修改所有调用与文档，不添加内部路径转发壳。

## 验证入口

- Python 行为测试使用 `scripts/run_tests.sh tests/hermes_cli/`；按修改选取文件，配置、认证和路由测试使用隔离的 `HERMES_HOME`。
- Desktop 接口需覆盖认证、Profile/连接归属、错误响应及相应前端消费方。
- 更新/启动改动按需覆盖 `tests/compat/`、Gateway 生命周期和原生宿主行为；Windows 结果不能由 macOS 模拟替代。
- 仓库检查使用 `python scripts/check --base HEAD`；纯文档更新核对链接和产品范围，无需运行全部业务测试。
