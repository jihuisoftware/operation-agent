# 当前开发交接记录

记录日期：2026-10-31。基准提交：`d73cf74728`。恢复时先核对 `git status --short` 和 `git rev-parse --short HEAD`；本记录不替代代码、规则或用户最新指令。以下工作均尚未提交，保留现有修改。

## 当前任务：桌面代码存量分析与界面更名

已完成 `apps` 下 Desktop、共享代码与安装器的静态审查，证据和清理顺序见 [Desktop 代码存量分析](desktop-code-audit.md)。重点：MCP 页面隐藏后仍保留后台检查与深链接线；退役功能仍有 SDK/设置 UI 残留；多平台安装与启动分支尚存；主进程 18,318 行。没有批量删除代码，未将共享协议与远程平台支持判作死代码。

聊天首页、首次设置、安装提示、条款提示、版本命令说明和 HTML 标题已改为用户指定的“营运智能体”。外部门户引用、CLI/包名及应用身份不变。顺带修正引导测试仍匹配旧英文标题的问题。

本次验证：聊天首页与引导测试共 5 项通过，Desktop 完整类型检查通过，`python scripts/check --base HEAD` 的 12 项检查通过，`git diff --check` 通过。未开启浏览器或操作真实账号；开发模式刷新页面可见文案，安装包需要重新构建。

## 前序任务：修复小红书登录识别与状态保留

用户反馈登录后状态不变，并要求已登录状态持续保留直至明确失效。已修复：

- 回归测试复现频道侧栏中头像链接与“我”标签分离时漏识别；扩展账号导航结构，并验证检测函数可序列化到隔离网页执行。
- 页面就绪后每 2 秒检查登录变化，更新后通知界面刷新；避免网页尚未就绪时读取失败。

- 蓝图、任务与执行及运营工作台加入平台登录状态，覆盖小红书、知乎、B 站、微信公众号后台、抖音。
- 只读识别内嵌页面的账号导航、登录及验证标志；不确定时显示“无法确认”，不把公开文章或笔记作者视作当前账号。
- 最近检查与明确登录证据分开存储，并迁移旧的明确记录。时间经过、离线、换窗口、unknown 或验证码均不清除已登录；最新明确退出覆盖旧窗口的登录记录。
- 在线情况、账号不匹配、验证要求单独展示；状态仍按 Profile 隔离，确认时间不因静态 DOM 重读而更新。
- “检查／登录”先暂停当前规则并等待正在执行的操作退出，再使用同一内嵌页面；不打开系统浏览器。登录完成后由用户回工作台恢复。
- 小红书账号与运营规则不一致会提示；登录或验证要求在应用内提示。登录状态不改变授权和额度，实际任务仍执行原有账号与结果核对。
- 私有 API `/platforms` 与 `/platforms/observe` 继承认证及 Profile 归属；只接收状态和账号标识，不接收 Cookie、密码、令牌或正文。

入口：前端 `apps/desktop/src/plugins/operations/platform-logins.tsx`、`use-platform-login.ts`、`login-page.ts`；后端 `plugins/operations/login_status.py`。完整路由见 [代码导航](code-map.md)，使用说明见 [运营插件 README](../plugins/operations/README.md)。

## 验证

| 命令或范围 | 结果 |
| --- | --- |
| `scripts/run_tests.sh`：`tests/plugins/test_operations.py`、`test_operations_http.py`、`test_operations_workflow.py`、`test_operations_blueprints.py`、`test_operations_login_status.py` | 32 项通过，临时 Profile 和模拟来源/模型/网页 |
| `npm run test:ui --workspace apps/desktop -- src/plugins/operations src/app/cron` | 97 项通过；账号导航标签兼容调整后，`login-page.test.ts` 定向复验通过 |
| UI 测试宿主配置 | `NODE_OPTIONS=--no-experimental-webstorage` |
| `npm run typecheck --workspace apps/desktop` | 通过，包含最后新增的 Worker 测试 |
| `python scripts/check --base HEAD` | 12 项检查通过；ESLint 与 `git diff --check` 通过 |

## 保留的前序工作

- 运营蓝图：八项模板、三步配置、草稿与启用分离；每 Profile 一套计划与 Cron，幂等应用、旧规则迁移、独立内容生产与发布、模块排期和历史保留。
- 开发上下文优化：功能导航、聚焦阅读工作流及本交接记录；根 → Desktop → src 指引精简约 18%，关键约束保留。
- 根 README、运营插件说明及 MVP 状态均包含上述功能。

## 约束与后续边界

- 不使用 computer use；本次测试不打开真实平台或操作真实账号。网页检测器按模拟 DOM 验证，实际站点结构与登录流程仍待明确授权后的联调。
- 其他平台登录入口不代表已新增其自动发布适配器。登录观察只适用于运营执行页，不继承聊天预览或系统浏览器登录状态。
- Server 和 Desktop 重启后生效。已确认的历史登录状态保留，窗口可执行状态单独显示；原先未识别成功的账号需要在内嵌页重新检查一次。
- 大文件拆分尚未实施；后续按明确任务逐步处理。当前没有待执行的真实账号动作。
