# Gateway 通信与 RPC 分层

原 `tui_gateway/` 已并入 `gateway/`，不再提供旧 Python 包的转发层。桌面正常启动仍使用 `hermes gateway ensure --json`，连接同一个 Gateway 后台；目录拆分不代表独立服务。

| 位置 | 职责 |
|---|---|
| `gateway/run.py`、`run_*.py` | 启动、调度、后台生命周期 |
| `gateway/session_*.py` | 会话权威、持久队列、执行、恢复与原生客户端操作 |
| `gateway/rpc/` | 辅助 RPC、共享投影和保留的内部处理器；`server.py` 是门面 |
| `gateway/transport/` | WebSocket、内部 stdio、事件回放、审批请求与受限辅助派发 |
| `gateway/contracts/` | Python 协议模型，生成 TypeScript/OpenRPC |
| `gateway/runtime/` | Profile 启动作用域、Git 探测和独立运行辅助模块 |

## 桌面请求路径

Electron 获得一次性票据 → `gateway/run_api.py` 验证连接 → `gateway.transport.ws.handle_ws` → `gateway.session_controls.AuthorityConnection`。会话操作由会话权威持有；它不接受的部分辅助方法，只有在 `ws_legacy_fallback.py` 允许且票据能力足够时，才进入 `gateway.rpc.server`。

辅助回退不能绕过会话权威的写入、代次或 Profile 边界。worker-adoption 票据不能取得完整交互客户端能力。旧处理器不应另建一套权威来处理同一会话。

## 协议与交互

- `contracts/canonical*.py` 声明原生会话接口；其他 contracts 文件声明辅助 RPC、事件和服务端请求。两份目录的同名方法不一定具有相同参数或结果。
- `transport/server_requests.py` 处理 approval、clarify、secret 等双向请求。回复必须匹配请求与所属 transport；断线、取消和恢复保持原有归属。
- `transport/event_replay.py` 与 `transport/transport.py` 负责事件序列、重放和客户端扇出。它们不拥有业务会话。
- `transport/entry.py` 仅保留内部 stdio/测试入口，不能与已有 Gateway 同时写同一 Profile。它不是终端聊天 UI，也不再创建 PTY 回连发布器。
- `pet.cells`、`learning.frames` 两个终端渲染 RPC 已移除。Desktop 的宠物元数据、精灵图与其他在用接口保留。未知方法按现有 JSON-RPC 错误返回。

## Handler 门面和作用域

`rpc/method_ctx.py` 将 sibling 的函数绑定到 `rpc/server.py` 命名空间；handler 中的裸全局变量由门面持有。测试必须 patch 实际读取位置，不要把导入路径迁移变成另一份模块状态。

`runtime/launch_profile_policy.py` 管理 Profile 的 home、secret、terminal scope。每次 RPC、定时器、线程切换、关闭或驱逐均绑定所属 Profile，不能从启动环境借用另一个 Profile 的密钥。配置缓存的刷新遵守原有会话边界，不因迁移重建正在使用的系统提示词或工具集。

保留历史协议名、会话 source、`HERMES_TUI_*` 兼容输入和已有日志文件名；这些值不是可导入的 Python 包路径。更新进程辨识仍识别升级前的进程形态。

## 保留的内部模块

Bot relay、hosted room、MCP、子任务、审批和连接器模块仍有内部消费者或兼容契约，不按旧 UI 名称删除。是否向用户或模型开放，由现有产品范围与权限规则决定；本次整合不恢复已关闭的工具或服务。

## 验证与开发入口

```sh
scripts/run_tests.sh tests/gateway/rpc/ tests/gateway/contracts/
python scripts/gen_gateway_contracts.py
npm run typecheck --workspace apps/desktop
```

所有测试通过项目测试环境运行。修改协议后生成 TypeScript/OpenRPC，核对在用方法及保留 schema 的字段没有意外变化。对初始化、子进程或打包改动，还需检查从干净工作目录导入、源码根目录定位和包发现。

参考：[Gateway 规则](../gateway/AGENTS.md)、[RPC 规则](../gateway/rpc/AGENTS.md)、[代码地图](code-map.md)。
