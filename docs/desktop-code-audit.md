# Desktop 代码存量分析

日期：2026-10-31。基于当前工作树及基准提交 `d73cf74728`。本次做静态引用、产品配置与提交历史核对，修改界面名称；未批量删除功能，也未做运行时性能采样。

## 结论

`apps` 确实保留了较多上游通用桌面的代码。当前问题同时包括退役功能的残留接线、仍需兼容的共享能力，以及过大的业务文件，不能将这些全部视作死代码。没有足够证据给出“可删除代码百分比”。

产品范围以 `hermes_cli/data/operations-profile.json` 为准。提交 `5b570f6e94` 明确裁掉 MCP/连接器等页面入口；当前 `capabilities/index.tsx` 仅注册技能和工具两个页签。Bot、Kanban、Radio 的插件主体已不在 `src/plugins`，目前这里只有运营插件，旧注释中“保留为 dormant libraries”的描述已过时。

## 主要发现与处理顺序

| 优先级 | 发现与证据 | 建议及边界 |
| --- | --- | --- |
| 高 | MCP 页面已隐藏，但 `src/app/contrib/hooks/use-desktop-integrations.ts` 仍启动 `startMcpHealthChecker()`；`src/store/mcp-health.ts` 在连接后及每 30 分钟读取配置并检查启用的 HTTP/SSE 服务，没有运营产品开关判断。 | 先统一产品开关与后台生命周期，避免隐藏功能仍发起无用请求或提示。是否真正触发探测取决于保存的配置和后端，不据此断言启动延迟。 |
| 高 | 同一 integrations hook 仍接收 `hermes://mcp/install`；`src/app/contrib/wiring.tsx` 仍挂载 `McpInstallDeepLinkDialog`，后者可写入 MCP 配置。 | 将深链和对话框一并纳入产品范围控制；保留后端 MCP 内部契约，避免只删页面留下旁路。 |
| 中 | `src/app/settings/config-subpages.ts` 不再提供 delegation 子页，但 `config-settings.tsx` 仍导入委派路由与子代理模型组件；`settings/delegation/` 保留完整编辑器。 | 核对嵌入式消费者后移除退役设置 UI。共享会话中的子代理事件、历史消息呈现需要另行判断，不能按关键词删除。 |
| 中 | `src/app/capabilities/mcp/`、`connectors/`、`plugins/plugins-tab.tsx` 保留原界面；`src/sdk/index.ts` 仍导出 `ConnectorsTab`。 | 页面入口移除不等于无人引用；先审查 SDK 消费者及运行时插件，再缩减相关组件和翻译。设置中的插件管理仍服务运营插件，须保留。 |
| 中 | `platform-policy.cjs` 和打包钩子限定 macOS，`electron/` 仍有 Windows、Linux、WSL 的启动、GPU、沙箱等模块；`main.ts` 仍引用 Linux GPU 与 WSL bridge。 | 优先隔离本机平台分支，之后删除不支持的本机实现。Mac 连接远程 Linux/Windows 主机的能力不能随之误删。 |
| 中 | `apps/bootstrap-installer` 是另一套 Tauri 安装器，保留 PowerShell 与 shell 的跨平台安装实现；根 `package.json` 的 `apps/*` workspace 和 `.github/workflows/stable-release.yml` 仍引用它。 | 先确认本产品发行链是否需要该安装器，再连同工作区、锁文件和 CI 一起退役。它有 macOS 实现，不能简单当成纯 Windows 目录删除。 |
| 中 | `src/sdk/index.ts` 仍有 `workspaceMode === 'bots'` 路由分支、Kanban 相关说明；`src/contrib/plugins.ts` 的注释与当前目录不符。 | 优先清理旧注释，再按调用关系收敛 SDK。退役插件/路由过滤器用于阻止旧配置或外部插件恢复入口，应保留。 |
| 中 | `electron/main.ts`、会话控制与翻译类型文件仍非常大。 | 按主题抽出窗口生命周期、连接、安装更新等模块；优先拆实际修改频繁的文件。这些是维护负担，不代表内容都过时。 |

## 规模与统计口径

统计 `.ts/.tsx/.js/.jsx/.mjs/.cjs` 文件，排除 `node_modules`、`dist`、`target`、`build`；以文件名 `.test.` / `.spec.` 区分测试，因此“其他代码”仍包括类型、测试辅助和生成文件，不等于生产逻辑规模。

| 范围 | 其他代码文件 / 行数 | 测试文件 / 行数 |
| --- | ---: | ---: |
| `apps/desktop/src` | 1,588 / 340,453 | 1,227 / 243,060 |
| `apps/desktop/electron` | 322 / 78,489 | 335 / 64,787 |
| `apps/shared/src` | 33 / 12,566 | 15 / 2,283 |

以上为修改文案前的快照。大文件例子：

- `apps/desktop/electron/main.ts`：18,318 行；应逐步拆分职责。
- `apps/desktop/src/app/session/hooks/use-session-actions/index.ts`：3,420 行；会话动作协调值得继续拆分。
- `apps/desktop/src/i18n/zh.ts`：4,953 行；`i18n/types.ts`：4,297 行；按功能分组，并随已确认退役的消费者清理文案。
- `apps/shared/src/gateway-contract.generated.ts`：7,203 行；这是生成的共享协议，应从生成源治理，不能按 Desktop 当前入口手动裁剪。

`apps/shared` 中 JSON-RPC、会话与连接契约仍被 Desktop 使用，应保留。代码行数和隐藏入口均不能直接证明启动性能问题；后续性能优化需测量构建、Electron 就绪和渲染挂载耗时。

## 本次已完成

聊天首页、首次设置、安装进度、条款提示、版本命令说明及 HTML 页面标题改为“营运智能体”。保留外部 Nous 门户页面引用“Hermes Agent”、CLI 命令、包名、应用 ID 和用户数据目录，避免影响外部指引和已有安装。

核验使用现有聊天首页及引导界面测试、Desktop 类型检查和仓库检查；不启动真实平台网页，不操作账号。下一步宜先处理 MCP 残留后台接线，再分批清理已无消费者的界面，最后收敛平台实现和拆分大文件。
