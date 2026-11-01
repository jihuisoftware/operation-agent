# 按功能定位代码

这是入口索引，不是完整文件清单。先选当前任务对应的一行，再按根 [AGENTS.md](../AGENTS.md) 的路由读取区域约束；不要一次加载表中的全部目录。移动入口时同步更新本表，路径和符号以工作树为准。

| 功能或问题 | 首先定位 | 需要跨层时再查 | 验证入口 |
| --- | --- | --- | --- |
| 配置先选择后自定义、日期与时间控件 | [运营选择控件](../apps/desktop/src/plugins/operations/configuration-choices.tsx)、同目录 `configuration-presets.ts` / `blueprint-fields.tsx` | [普通 Cron 时间选择](../apps/desktop/src/app/cron/schedule-picker.tsx)；沿用已有规则字段和 Cron 表达式协议 | `configuration-choices.test.tsx`、`blueprint-library.test.tsx`、`schedule-picker.test.tsx`、Cron `index.test.tsx` |
| 运营总览、导航排序与管理详情入口 | [总览页面](../apps/desktop/src/plugins/operations/overview.tsx)、[插件导航](../apps/desktop/src/plugins/operations/plugin.tsx) | [SQLite 汇总](../plugins/operations/overview.py)、`dashboard/plugin_api.py` 私有 `/overview`；`workbench-page.tsx` 管理分区跳转 | `overview.test.tsx`、`tests/plugins/test_operations_overview.py`、`test_operations_http.py` |
| 应用图标与界面品牌标识 | [运营矢量图标](../assets/operations-mark.svg)、[统一生成器](../scripts/generate_icons.py) | `apps/desktop/assets/icon*`、`components/brand-mark.tsx`；macOS 分层图标见 `scripts/mac-icon.cjs` | `tests/scripts/test_icon_flavors.py`、`test_icon_generation_exit.py`，生成器 `--check` |
| 侧栏任务执行动态图标 | [指示器](../apps/desktop/src/app/chat/sidebar/navigation-task-activity.tsx)、[执行状态](../apps/desktop/src/store/navigation-activity.ts) | `store/task-activity.ts` 负责按连接/Profile 观察；插件通过 `SidebarNavContribution.activity` 提供状态 | `task-activity.test.ts`、`navigation-activity.test.ts`、`navigation-task-activity.test.tsx` |
| 实时状态、待执行任务、人工取消步骤 | [实时状态](../apps/desktop/src/app/activity/index.tsx)、[待执行任务](../apps/desktop/src/app/upcoming/index.tsx)、[侧栏导航](../apps/desktop/src/app/chat/sidebar/navigation.tsx) | [普通任务单次取消](../cron/upcoming.py)、[运营时段取消](../plugins/operations/upcoming.py)、`sdk/cron.ts` 的 `renderUpcoming` | `tests/cron/test_upcoming.py`、`tests/plugins/test_operations_upcoming.py`、`tests/hermes_cli/test_cron_upcoming.py`；前端同目录测试 |
| 任务计划、实时步骤、数据库历史 | [详情组件](../apps/desktop/src/app/cron/task-details.tsx)、[通用任务日志](../cron/task_history.py)、[详情接口](../hermes_cli/web_routers/cron_task_detail.py) | [运营进度投影](../plugins/operations/progress.py)，`store.py` / `runtime.py` 的执行关联 | `task-details.test.tsx`、`tests/cron/test_task_history.py`、`tests/hermes_cli/test_cron_task_detail.py`、`test_operations_manual.py` |
| 运行记录展开、复制、完整输出 | [记录组件](../apps/desktop/src/app/cron/run-record.tsx)、[原文读取](../hermes_cli/web_routers/cron_run_output.py) | `web_routers/cron.py` 的摘要和记录关联；运营实际结果见 `plugins/operations/outcomes.py`、`manual.py` | `run-record.test.tsx`、`tests/hermes_cli/test_cron_run_output.py`、`test_operations_manual.py` |
| 定时与手动执行冲突、运行状态 | [调度认领](../cron/occurrences.py)、[执行台账](../cron/executions.py)、[任务状态](../apps/desktop/src/app/cron/job-state.ts) | `cron/jobs.py` 的到期扫描、`cron/scheduler.py` 的进程内注册 | `tests/cron/test_manual_tick_overlap.py`、`job-state.test.ts`、`index.test.tsx` |
| 场景模板、运营蓝图、三步配置 | [蓝图库](../apps/desktop/src/plugins/operations/blueprint-library.tsx)、同目录 `blueprint-wizard.tsx` / `blueprint-fields.tsx` / `blueprint-types.ts` | [六项场景定义](../plugins/operations/scenarios.py)、[目录、预览与应用](../plugins/operations/blueprints.py)、[定时任务贡献区](../apps/desktop/src/app/cron/contributed-blueprints.tsx) | `blueprint-library.test.tsx`、`tests/plugins/test_operations_blueprints.py` |
| 业务主题、子类、默认定位 | [业务默认配置](../plugins/operations/business_themes.py)、[业务选择与修改](../apps/desktop/src/plugins/operations/business-fields.tsx)、同目录 `business-config.ts` | `policy.py` 校验主题与子类；`blueprints.py` 目录与持久化；旧规则通过默认空字段兼容 | `tests/plugins/test_operations_business_themes.py`、`blueprint-library.test.tsx` |
| 运营规则、账号权限、额度 | [规则](../plugins/operations/policy.py)、[模块与旧规则转换](../plugins/operations/modules.py) | [事务台账](../plugins/operations/store.py)、`migration.py`、[工作台](../apps/desktop/src/plugins/operations/workbench.tsx) | `tests/plugins/test_operations.py`、`test_operations_blueprints.py` |
| 开发单任务、整链路测试与日志复制 | [调试页](../apps/desktop/src/plugins/operations/debug/panel.tsx)、同目录 `records.tsx`；[开发后端](../devtools/operations_debug.py)、[整链路编排](../devtools/operations_pipeline.py) | Vite 仅 serve 注册；接口按源码和 Profile 开关挂载，发布快照排除 devtools；发布绑定本批版本，分步事件入库 | `tests/devtools/test_operations_pipeline.py`、`test_operations_pipeline_http.py`（私有 HTTP 全链路）、`tests/plugins/test_operations_debug.py`、`tests/scripts/test_operations_debug_distribution.py`、`debug/*.test.tsx` |
| 每日执行、暂停、恢复 | [运营 tick](../plugins/operations/runtime.py)、[手动批次](../plugins/operations/manual.py)、[业务阶段](../plugins/operations/workflow.py) | 同目录 `occurrences.py`（最近一次补执行与待执行列表）、`recovery.py`；仅调度底层问题才进入 [Cron](../cron/AGENTS.md) | `tests/plugins/test_operations_workflow.py`、`test_operations_manual.py` |
| 资料整理与分类分析 | [增量整理](../plugins/operations/organization.py)、[资料目录](../plugins/operations/organization_catalog.py)、[分类页面](../apps/desktop/src/plugins/operations/organized-library.tsx) | 私有 `/organized-sources`；`topics.py` / `content.py` 消费整理资料并记录引用；`modules.py` / `migration.py` | `test_operations_organization.py`、完整流程与整链路调试、`organized-library.test.tsx` |
| 分轮检索、失败重试与读取额度 | [采集编排](../plugins/operations/collection.py)、`collection_search.py`、`collection_ledger.py`、`collection_validation.py` | `tools/web_document_metadata.py` 内部元数据；来源素材库 `collection-summary.tsx` 展示批次 | `test_operations_collection.py`、`test_web_document_metadata.py` |
| 独立采集、选题与手动题目 | [采集](../plugins/operations/collection.py)、[选题服务](../plugins/operations/topics.py)、[选题管理](../apps/desktop/src/plugins/operations/topics-panel.tsx) | `modules.py` / `migration.py` 的 schema 4；`content.py` 消费选题；`workbench-rules.tsx` / `blueprint-fields.tsx` 简化主题设置 | `test_operations_topics.py`、`test_operations_workflow.py`（`tests/plugins/`），`topics-panel.test.tsx` |
| 来源图文素材、图片保存与历史复用 | [来源素材库](../apps/desktop/src/plugins/operations/source-library.tsx)、[素材服务](../plugins/operations/source_library.py)、[参考图片](../plugins/operations/source_media.py) | 私有 `dashboard/source_api.py`；`collection.py` 采集保存图片，`topics.py` / `content.py` 读取当日和当前主题已选历史来源；参考图片与发布资产分开 | `tests/plugins/test_operations_source_library.py`、`source-library.test.tsx` |
| 内容生产、版本、素材 | [内容生产与检查](../plugins/operations/content.py)、[人工管理服务](../plugins/operations/service.py) | [内容编辑](../apps/desktop/src/plugins/operations/management.tsx)、`workflow.py` 的 `publish` | `test_operations_blueprints.py`、`test_operations_http.py`（均在 `tests/plugins/`） |
| 自动运营网页、发布和互动 | [后台执行器](../apps/desktop/src/plugins/operations/worker.tsx)、同目录 `browser.ts` / `page.ts` | `execution-clock` 后台时钟、`browser-navigation` 导航完成事件、`page-ready` 就绪检查；[私有 API](../plugins/operations/dashboard/plugin_api.py)、`store.py` 原子入队 | 同目录 `worker.test.tsx` / `browser*.test.ts` / `page.test.ts`；`test_operations_dispatch.py`、恢复及完整模拟日测试 |
| 运营画面工作图标 | [入口按钮](../apps/desktop/src/plugins/operations/live-view-button.tsx)、`state.ts` | `worker.tsx` 在网页命令开始/结束更新状态，按连接/Profile 隔离 | `live-view-button.test.tsx`、`worker.test.tsx` |
| 运营画面空白、登录保持 | [网页生命周期](../apps/desktop/src/plugins/operations/use-operations-guest.ts) | `worker.tsx` 按连接/Profile 挂载；与 API 轮询分离，兼容原有持久化分区 | `use-operations-guest.test.tsx`、`worker.test.tsx` |
| 账号登录独立页面 | [账号页面](../apps/desktop/src/plugins/operations/accounts.tsx)、同目录 `platform-logins.tsx` / `use-platform-login.ts` / `login-page.ts` | [检查与登录确认](../plugins/operations/login_status.py)、私有 API；`plugin.tsx` 注册侧栏 `/accounts`，复用运营 worker 的内嵌页面 | `accounts.test.tsx`、`login-page.test.ts`、`platform-logins.test.tsx`、`use-platform-login.test.tsx`；`tests/plugins/test_operations_login_status.py` |
| 日报、指标、复盘 | [日报](../plugins/operations/report.py)、同目录 `feedback.py` | `store.py` 的持久化记录；工作台导出入口 | `tests/plugins/test_operations_workflow.py` |
| 定时任务主页面、手动执行 | [Cron 页面](../apps/desktop/src/app/cron/index.tsx)、同目录 `cron-actions.ts`；[工作区路由](../apps/desktop/src/app/contrib/surfaces.tsx) | [HTTP 路由](../hermes_cli/web_routers/cron.py)、`cron/jobs.py` / `scheduler_*.py` | `apps/desktop/src/app/cron/` 同目录测试；`surfaces.app-routes.test.tsx`；`tests/cron/` |
| 聊天中的实时网页 | [右侧预览](../apps/desktop/src/app/chat/right-rail/preview.tsx)、[预览归属](../apps/desktop/src/store/preview-ownership.ts) | [页面操作工具](../tools/drive_preview_tool.py)、[浏览 RPC](../tui_gateway/methods_browser.py) | `apps/desktop/src/store/preview-*.test.ts`、Electron `preview-*.test.ts` |
| 模型列表、提供方、设置 | [模型设置](../apps/desktop/src/app/settings/model-settings.tsx)、同目录 `model-select.tsx` | [模型 API](../hermes_cli/web_routers/models.py)、[模型目录](../hermes_cli/model_catalog.py)、`tui_gateway/model_switch.py` | `model-settings.test.tsx`；在 `tests/hermes_cli/` 搜索对应符号 |
| Desktop 启动、连接、会话 | [Electron 入口](../apps/desktop/electron/main.ts)（只搜索相关符号）、同目录 `backend-*.ts` / `local-gateway-*.ts` | [Gateway 运行时](../hermes_cli/gateway_runtime.py)及同前缀兄弟模块；[会话创建请求](../apps/desktop/src/app/session/hooks/use-session-actions/session-create-request.ts) | Electron 同目录测试、`session-create-request.test.ts`；Gateway 对应测试 |
| 产品能力显示与裁剪 | [产品范围](../hermes_cli/data/operations-profile.json)、[Desktop 范围读取](../apps/desktop/src/lib/operations-profile.ts) | [产品状态与启动说明](../README.md)、[MVP 状态](operations-platform-mvp.md) | `apps/desktop/src/lib/operations-profile.test.ts` |

聊天预览与运营执行器有不同的生命周期和归属；先确认用户指的是哪一个。运营业务修改优先留在插件里，定时任务核心只负责通用贡献入口；SDK 契约在 [cron.ts](../apps/desktop/src/sdk/cron.ts)。

## 共享运行时的入口

只有问题确实跨越业务边界时才继续：

| 领域 | 定位方式与约束 |
| --- | --- |
| 模型执行、上下文、记忆 | `run_agent.py` 为入口，按主题找 `agent/turn_*.py`；规则见 [agent/AGENTS.md](../agent/AGENTS.md) |
| CLI、配置、私有 HTTP 服务 | `cli.py` / `hermes_cli/cli_*_mixin.py`；`hermes_cli/web_server*.py`；规则见 [hermes_cli/AGENTS.md](../hermes_cli/AGENTS.md) |
| Gateway、JSON-RPC、Profile | `gateway/run*.py`、`tui_gateway/`；规则分别见 [Gateway](../gateway/AGENTS.md)、[RPC](../tui_gateway/AGENTS.md) |
| 会话存储、Profile 路径 | `hermes_state.py` / `hermes_state_*.py`；`hermes_constants.py` 的 `get_hermes_home()` |
| 工具、技能、插件 | `model_tools.py` / `toolsets.py` / `tools/registry.py`；按根路由读取对应 AGENTS；不要为找一个工具读取全部注册表 |
| 环境、依赖、机器事实 | `pm/`、`hermes_platform/`；按根路由读取对应约束，不直接修改托管环境 |

定位示例和最小验证命令见 [开发工作流](development-workflow.md)。恢复上次工作时看 [任务交接记录](dev-handoff.md)，并先核对工作树。
