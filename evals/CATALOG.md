# 保留项索引

本索引按目录族和根脚本覆盖保留代码；`fixtures.py`、任务数据、报告模块和前端夹具随所属评测族管理。目录不是一键执行单元。

**状态（2026-11-09）：以下手动入口均未在本轮完整复跑，当前 SHA/系统的通过状态未知。** “本地/无模型”来自脚本声明与静态阅读，不是运行收据。费用或隔离未核验的条目先按“可能访问网络、使用凭据、写入状态”处理。正式回归的实际结果见开发交接记录。

## 目录族

| 目录/说明 | 用途 | 运行条件、费用和输出边界 |
|---|---|---|
| [browser_use](browser_use/README.md) | 浏览器工具路径 A/B | 真实模型、网页与浏览器；可能付费；输出由 --results 指定 |
| [codebase_navigability](codebase_navigability/README.md) | 代码定位效率与静态复杂度 | 需要独立基准环境；静态/模拟与运行时基准分开，详见 README |
| [codex_echo](codex_echo/README.md) | 响应回显与本地协议复现 | fixture_server.py 与 probe.py 配合；完整运行条件未复核 |
| [compaction](compaction/README.md) | 压缩召回、政策和循环退化 | 真实辅助模型可能付费；--out 与历史会话副本；详见 README |
| [core_tool_deferral](core_tool_deferral/README.md) | 核心工具延迟暴露的研究 | 真实模型 A/B；需基准/候选源码和沙箱；不恢复当前禁用工具 |
| [dashboard_auth](dashboard_auth/) | 私有后台认证刷新与并发 | 本地完整链路探针；认证服务/输出参数待核验 |
| [delegation_group_schema](delegation_group_schema/README.md) | 内部 delegation 分组契约 | 内部兼容研究；不代表开放委派工具；详见 README |
| [desktop-pane-fixture](desktop-pane-fixture/README.md) | 前端模块加载延迟复现 | 在 apps/desktop 执行 README 中的 vitest；无模型推理；会注入加载延迟 |
| [desktop_bug_campaign](desktop_bug_campaign/) | 界面、会话、租约、重建专项复现 | 真实前端/后台与局部模拟；各脚本独立，需核验端口、临时目录和清理 |
| [desktop_gateway_ticket_native](desktop_gateway_ticket_native/README.md) | 原生 Electron main 连接与票据 | 真实 macOS Electron+临时 Gateway；无推理费用；--output 保存回执 |
| [desktop_mcp_oauth](desktop_mcp_oauth/README.md) | 桌面 MCP OAuth 生命周期 | 本地 HTTP fixture 与 renderer 驱动；不代表 MCP 服务已启用 |
| [gateway](gateway/) | 会话时间持久化 | 生产库 controls 与 A/B；按脚本要求使用隔离数据与输出 |
| [gateway_status_render](gateway_status_render/) | 轮次上限状态呈现 | 本地 A/B；需两个明确版本；覆盖边界见脚本 |
| [hosted_attachment_transfer](hosted_attachment_transfer/) | 附件传输性能 | 传输/存储专项；当前托管入口未复核，不作为桌面验收 |
| [liveness](liveness/) | WebSocket 断连与重连 | 真实本地会话/计时器，模型边界模拟；检查进程清理 |
| [native_compaction](native_compaction/) | 原生压缩检查点 | 专项 A/B；模型/外部服务和输出路径待复核 |
| [openrouter_pkce_ab](openrouter_pkce_ab/) | PKCE 认证流程对比 | 认证专项；是否访问真实服务按参数核验，先读 harness.py |
| [plugin_isolation](plugin_isolation/) | 插件隔离审计 | 复用生产隔离检查；输出是审计结果，不是插件功能测试 |
| [postmortem](postmortem/README.md) | 成本、缓存、目标和工具取证 | forensics 只读副本；live_ab/review_probes 分别核验费用与网络；详见 README |
| [prefix_rediet](prefix_rediet/README.md) | 固定前缀成本 A/B | 真实模型矩阵、隔离工作进程；可能付费；详见 README |
| [prompt_footprint](prompt_footprint/) | 工具属性说明的提示词体积 | 专项测量；完整运行方式待复核 |
| [provider_fallback](provider_fallback/) | 提供方回退问题复现 | 按问题编号保留；不能视为所有路由的兼容测试 |
| [provider_wire](provider_wire/) | 提供方报文与 SDK 边界 | 各 issue 脚本独立；模拟/真实调用范围待逐项核验 |
| [readtool](readtool/README.md) | 文件读取任务效果 | 真实模型、文件夹具、标签结果；可能付费；详见 README |
| [reasoning_replay](reasoning_replay/README.md) | 推理内容重放矩阵 | 真实路由调用可能付费；harness.py run/report；详见 README |
| [session_search_schema](session_search_schema/README.md) | 会话检索 schema 对比 | 真实模型+隔离样本库；可能付费；基准和候选 ref 必填 |
| [shared_gateway](shared_gateway/README.md) | Gateway 验收清单与独立驱动 | 各探针范围有限；统一驱动未完成；verify_receipt 只检查回执完整性 |
| [subagent_process_handoff](subagent_process_handoff/) | 内部子进程交接压力 | 真实编排器/子 agent；可能付费与启动长期进程；待复核 |
| [token_accounting](token_accounting/) | Token 来源、重放和图片成本 | 各脚本边界不同；输出使用 --out；模拟计数不可当提供方账单 |
| [tool_search](tool_search/README.md) | 工具检索与延迟调用研究 | 真实 OpenRouter 模型；可能付费；不恢复当前禁用的连接器 |
| [toolperf_abeval](toolperf_abeval/README.md) | 工具性能多模型 A/B | 真实模型矩阵；可能付费；结果依任务和重复次数变化 |
| [update_pipeline](update_pipeline/) | 更新中断与版本切换恢复 | 临时 Git 仓库/安装树；可能下载依赖，不用于生产安装 |
| [update_streaming](update_streaming/) | 更新过程的实时输出 | 运行更新路径；先核验临时安装范围和输出参数 |

没有局部 README 的条目，其启动命令尚未标准化：阅读目录内脚本的 docstring、参数解析和顶层行为后再运行，不自动拼接 `--help`。

## 根目录专项探针

| 入口源码 | 用途 | 已知边界（完整运行仍待复核） |
|---|---|---|
| [acp_empty_session_wire.py](acp_empty_session_wire.py) | ACP 空会话持久化 | 本地 HTTP 模型；无付费推理；临时 SQLite/stdio |
| [anthropic_proxy_thinking_replay.py](anthropic_proxy_thinking_replay.py) | 代理推理块重放 | 本地报文模拟；不能证明真实提供方行为 |
| [api_delegation_sync_probe.py](api_delegation_sync_probe.py) | API 内部交付绑定 | 无模型；要求独立 HERMES_HOME；内部兼容探针 |
| [approval_deny_dispatch.py](approval_deny_dispatch.py) | 拒绝审批后的派发 | 离线派发回执；不调用特权程序 |
| [auth_pool_controls.py](auth_pool_controls.py) | 凭据池交互控制 | PTY+隔离 home+本地 OAuth；具体命令待复核 |
| [auxiliary_resource_exhausted.py](auxiliary_resource_exhausted.py) | 辅助模型资源耗尽错误 | 本地 HTTP 契约；无提供方请求 |
| [codex_masked_replay_review.py](codex_masked_replay_review.py) | 遮蔽错误恢复重放 | 本地 HTTP；不代表在线提供方验收 |
| [cron_error_diagnostics.py](cron_error_diagnostics.py) | Cron 错误诊断 | 本地 I/O A/B；无推理、外部 API 或投递 |
| [desktop-reap-clock-pressure.cjs](desktop-reap-clock-pressure.cjs) | 桌面进程回收与时钟压力 | Node/进程压力探针；运行条件与清理待复核 |
| [fanout_resource_bench.py](fanout_resource_bench.py) | 并发资源消耗 | 资源基准；费用、并发和进程范围待复核 |
| [gemini_type_array_probe.py](gemini_type_array_probe.py) | Gemini schema 类型兼容 | 本地适配器与 SDK 校验；无 API 调用 |
| [goal_command_parity.py](goal_command_parity.py) | 目标命令语义一致性 | 真实存储、无模型；保留内部 CLI 语义参照 |
| [heartbeat_idle_wire.py](heartbeat_idle_wire.py) | 心跳与队列契约 | 复用 tests/gateway/fixtures/heartbeat_wire.py；本地存储/模拟传输 |
| [key_cmd_picker_live.py](key_cmd_picker_live.py) | key_cmd 模型选择 | 本地鉴权 HTTP、真实 helper 与 CLI PTY；需 --repo/--output |
| [output_caps_local_capture.py](output_caps_local_capture.py) | 输出限制的 SDK 报文 | 本地捕获；无付费推理 |
| [output_caps_surfaces.py](output_caps_surfaces.py) | 输出限制的执行面 | 本地执行对照；不调用推理提供方 |
| [process_result_receipt_probe.py](process_result_receipt_probe.py) | 后台进程结果回执 | 真实子进程 I/O，无模型；参数 REPO OUT_DIR |
| [session_snapshot_removal.py](session_snapshot_removal.py) | 会话快照与显式保存 | 配置/SQLite A/B，无提供方调用；内部旧路径待复核 |
| [update_obligation_identity.py](update_obligation_identity.py) | 更新义务身份 | 临时进程与状态文件 A/B；仓库路径为首个参数 |
| [vault_fill_live_e2e.py](vault_fill_live_e2e.py) | 浏览器凭据填充 | 真实 browser_exec 与 Chromium；先核验模拟站点、凭据和清理 |

## 不在本索引中直接执行的材料

- [archive/](archive/README.md)：历史报告和原始统计，不作为当前验收。
- [output_caps_scope.md](output_caps_scope.md)：输出限制的范围说明。
- 正式夹具的当前位置和验证命令见 [README](README.md#正式测试与夹具归属)。
- Bot Mode、Kanban、公网 Webhook、Linux 桌面启动/systemd/旧终端专项探针已删除；正式 Linux 进程契约夹具仍在 `tests/`，由原生平台标记控制。
