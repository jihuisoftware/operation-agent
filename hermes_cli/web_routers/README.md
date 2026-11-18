# Desktop 共享私有 HTTP API

本目录是桌面后台路由，不是旧 Web 前端。开发时同时遵守[根指引](../../AGENTS.md)、[hermes_cli 指引](../AGENTS.md)及本目录 [AGENTS.md](AGENTS.md)。

## 运行位置与请求路径

```text
Desktop 页面 / 插件 SDK
  → Electron 的 hermes:api 桥接
  → Gateway 内的 HTTP 监听器（gateway/run_api.py）
  → hermes_cli.web_server 组装的应用及认证中间件
  → 当前 Profile 的 router / helper
  → 数据查询、配置事务或业务服务
```

- `web_server.py` 组装应用和路由，`web_server_*.py` 按主题提供实现；Gateway 挂载它们，不为每个窗口启动一个独立 `serve` 后台。
- 本机原生 HTTP 请求通过私有控制通道获取票据，使用既有认证入口和 Profile 绑定；远程连接继续使用其既有连接契约。
- 原生聊天的 `/api/ws` 优先进入 `gateway/transport/ws.py`、`session_controls.py` 和会话权威，不是把所有聊天重新交给一个旧 Web 会话引擎。
- 这里的私有 HTTP API 与 `gateway/platforms/api_server.py` 保留的公共平台适配器不是同一入口；相似的 URL 不代表相同的认证或生命周期。

后台分层见 [Gateway 通信与 RPC](../../docs/gateway-rpc.md)，包职责见 [hermes_cli 导航](../README.md)。

## 功能分工

| 请求类别 | 入口示例 | 实现归属 |
| --- | --- | --- |
| 模型与设置 | [models.py](models.py)、[config_env.py](config_env.py) | 模型目录、配置和凭据服务 |
| Profile 与会话数据 | [profiles.py](profiles.py)、[sessions.py](sessions.py) | Profile 服务、会话权威及状态存储；保留所属 Profile |
| 定时任务与记录 | [cron.py](cron.py)、[cron_task_detail.py](cron_task_detail.py) | Cron 与业务任务台账 |
| 文件、状态与其他桌面能力 | [files.py](files.py)、[status.py](status.py) 等 | 对应服务和既有权限检查 |
| 插件业务 | `/api/plugins/<插件名>/...` | 插件自己的 router，由 `web_server_dashboard.py` 的发现与挂载机制接入 |

目录中保留的模块和兼容路由不等于全部对用户开放；以应用实际挂载、能力门控和产品配置为准。
当前消息平台、Bot 配对入口和公共 Webhook 接入已退役，不在此恢复。
旧 `web/` SPA、终端聊天及 PTY 路由也不恢复；泛用业务逻辑或历史恢复引用仍须保留。

## 修改规则

- 通用路由放入对应主题模块，通过现有应用组装入口挂载；业务插件接口留在插件内，不向共享 server 门面堆入运营专用逻辑。
- 新接口复用认证、连接和 Profile 归属校验；延迟任务及线程切换仍需绑定同一作用域，不能读取启动 Profile 的密钥或默认数据库。
- 写请求沿用所属服务的事务、幂等及修订号约束；不要从 HTTP handler 绕过会话权威直接重放提交。
- Desktop 插件使用当前 SDK；旧浏览器插件界面 SDK 不是它的替代品。不要挂回旧 SPA 或引入另一套后台认证。
- 后端权威状态与前端缓存分开。修改返回类型时核对 Desktop 消费方，避免仅更新 Python 字段却破坏界面。

## 验证

路由测试位于 `tests/hermes_cli/`，通过 `scripts/run_tests.sh` 使用隔离的 `HERMES_HOME`。
按接口覆盖未认证拒绝、Profile 隔离、响应契约及写入冲突；必要时同时覆盖 `tests/gateway/` 和 Desktop API 测试。
操作系统相关行为在对应宿主验收，不用 macOS 结果代替 Windows 原生测试。

相关规则：[Desktop](../../apps/desktop/AGENTS.md)、[桌面后端契约](../../apps/desktop/src/AGENTS.md)、[Gateway RPC](../../gateway/rpc/AGENTS.md)。
