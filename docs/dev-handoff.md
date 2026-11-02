# 当前开发交接记录

记录日期：2026-11-02；当前基于 `41e3796f51`。工作树有运营兼容清理及其他并行改动；本轮未重置索引或提交。恢复时核对 HEAD、暂存区和实际 diff。本文是证据，不授权外部动作。

## 最新完成：内置插件清理与运营目录筛选

本轮开始时 HEAD 为 `89d6644e24`，期间外部提交推进到 `41e3796f51`；未重置索引、
未提交，也未覆盖并行运营调度改动。删除 Google Meet、成就系统及其专属测试；
删除 Kanban Dashboard 清单、前端产物与 systemd 单元，保留 `plugin_api.py` 和共享底层。
旧 UI 探针随产物退役，保留 API 的测试改为显式挂载；Profile 隔离测试单独模拟插件准入。

`operations-profile.json.pluginCatalog` + `plugin_catalog_scope.py` 在 CLI、Dashboard、
首次推荐及工具目录搜索中统一筛选本地/缓存/在线结果。当前 826 条中展示 232 条，隐藏 594 条。
完整 YAML、封禁名单、显式安装/深链接查询、更新、迁移和已安装插件管理保持可用。
范围及导航见 `plugins/README.md`、`plugin-catalog/README.md`、`docs/code-map.md`。

验证：目录及安装专项 6 文件最终均通过（53 项）；工具/产品/目录文档 4 文件 31 项通过；
保留 Kanban API 37 项、构建输入 10 项通过。扩展 Web Server 回归 179 项通过、1 项失败：
`TestNewEndpoints::test_discord_toolsets_read_and_write_discord_platform` 仍假设产品开放 Discord，
读取列表时报 `KeyError: discord`；该用例和对应工具集实现未在本轮修改。
十二项仓库检查通过，差异检查通过；未运行真实账号、模型或服务发布操作。
日志：`tmp/operations-acceptance/plugins-scope-20261102/`。工作区尚未提交。

## 本轮并行完成：可选技能目录裁剪

`optional-skills/` 从 152 项裁剪为 57 项，删除 95 项及其专属脚本、模板和参考资料。
完整去留清单与理由见 `optional-skills/README.md`。保留内容、媒体、检索、表格、演示、
分析和电商能力；删除训练研发、代码委派、链上支付、游戏、健康设备、家居及退役产品技能。
`mcporter` 是独立按需 CLI，保留不等于启用内置 MCP；远程上游安装机制保持不变。

同步去除关联技能推荐，删除 10 个只覆盖已移除实现的测试文件，保留共用测试中的有效用例。
运行 `website/scripts/generate-skill-docs.py` 更新英文目录、技能页及侧栏，清理中文镜像和目录，
修复引用与安装示例；生成器也补齐既有小红书技能的目录入口。网站无链接指向本次删除的技能页。
未触及用户已安装技能、配置、凭证或核心运行时，不执行真实账号操作。

验证：`scripts/run_tests.sh tests/skills tests/website tests/tools/test_skills_hub.py`，
30 文件、1145 项通过、2 项按 Windows 平台跳过。覆盖作者规范、资源、文档与安装源行为。
`python scripts/check --base HEAD` 十二项通过，差异空白检查通过。
日志：`tmp/operations-acceptance/optional-skills-20261102/`。上轮 MCP 清理仍保留 27 项，见 `optional-mcps/README.md`。

## 本轮：移除旧运营数据兼容

基于 `41e3796f51`，用户要求开发阶段不维护旧数据和功能。代码已移除 `migration.py`、`workspace_migration.py`、`workspace_history.py`，以及旧页面跳转、历史待归属/人工归属、旧账号分区分支、旧选题确认及旧格式消耗回填。正常的新执行记录、日报、归档、权限核对、跨主题引用与账号去重继续保留。

- 新业务统一保存于 `topics/<ID>.db`；目录从默认值建立，首次计划未启用。旧格式拒绝并返回清理提示，不自动转存、备份或导入。
- 多主题请求必须明确业务/主题，单一主题可直接访问；`hermes ops workspaces` 可查询目录。聊天状态查询在多主题时返回目录供选择。
- `scheduling.py` 将共享 Cron 身份保存到 Profile 目录，不再借用原计划。手动请求按主题排队；直接手动触发共享 Cron 为启用主题建立请求。新执行步骤统一携带主题前缀。
- README、插件 README、代码地图已更新。既有 APP 简化、节省 Token 和多业务隔离保留；没有操作真实账号发布/互动。

## 实际开发数据清理已完成

用户已明确确认清空 `/Users/dm/hermes-operations-dev` 的全部运营数据并重建。先停止开发 Gateway，删除旧迁移备份约 5.6 MB；确认全部清空后，又删除 212 个运营数据文件、1 个运营 Cron 及其 1,000 条执行记录。模型凭证、应用配置与 Cookie 文件未删除；其他 Profile 和其他任务未清理。

已建立 1 个空白业务、1 个空白主题，计划未启用；来源、素材、执行记录、外部动作、网页命令和待执行请求均为空。旧 `data.db` 与迁移备份不存在。页面访问会正常生成就绪条件记录，不是旧业务数据回流。Gateway 随后被开发环境重新启动，已通过状态命令确认运行（最后观测 PID 49221）。没有执行真实发布或互动。

补充“返回当前业务”入口：清空后残留旧范围 URL 时可进入新业务，不尝试查找或恢复旧记录。下一步在 Desktop 刷新/重开后从首页重新配置业务及登录新账号空间即可。

## 验证

- 后端运营回归 31 文件 154 项：首轮 153 通过，状态工具查询一项失败已修正；对应文件 11 项复测全过。覆盖两个业务四个主题的模拟整链路、隔离、调度、额度和新建。
- Desktop 29 文件 102 项通过；清空后失效 URL 的恢复入口补测文件 5 项通过。类型检查及修改范围 ESLint 通过。
- `python scripts/check --base HEAD` 十二项通过，差异空白检查通过。日志：`tmp/operations-acceptance/remove-legacy-20261102/`。
- 使用既有 PM 测试解释器与 `scripts/run_tests.sh`，没有更改依赖环境。没有使用 computer use，也没有进行 Electron 实机验收。

此前六主入口、快速开始、单份计划设置、后台网页执行和节省 Token 设置均保留。本轮没有修改或重置其他并行改动及索引；恢复时以当前工作树和最新用户授权为准。
