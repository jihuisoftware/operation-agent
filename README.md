# 通用运营平台

基于 Hermes Agent 的通用运营平台，主题由用户自行输入或选择，不限定行业、品牌或业务阶段。首批渠道为公众号、小红书和抖音，按用户需要选择。主要入口为 **macOS Desktop**，界面仅支持**简体中文**。

当前已完成运营范围配置与桌面入口收缩，保留模型调用、记忆、技能、文件处理、浏览器、终端和定时任务。素材台账、内容版本审核、发布回填与增长报表仍待实现；完整计划见 [MVP 方案](docs/operations-platform-mvp.md)。

## 产品范围

| 状态 | 范围 |
| --- | --- |
| 已保留 | Desktop 聊天、内容预览、文件处理、检索、浏览器、记忆、技能、待办、定时任务 |
| 按服务配置可用 | 图像理解、图片生成、视频理解、配音；实际能力取决于模型与服务 |
| 当前关闭 | 多 Agent 协作工具、Kanban 工具及自动派单、MCP 服务、公共 API／Webhook、自动技能整理、插件自动更新检查 |
| 已移除的入口 | Bot Mode、Kanban／Radio 界面、内置消息平台适配器、浏览器 Dashboard 前端、Windows 打包 |
| 待开发 | 品牌与素材台账、三平台内容包、版本审批、发布与互动记录、指标导入和复盘 |

工具与服务范围由 [operations-profile.json](hermes_cli/data/operations-profile.json) 定义，Python 与 Desktop 共用。macOS 限制由 [平台策略](apps/desktop/platform-policy.cjs) 实施，Desktop 语言由 [语言策略](apps/desktop/src/i18n/languages.ts) 固定为中文。旧配置不会重新开放已关闭的能力；配置覆盖不改写用户原始配置文件。

保留 delegation、Kanban、MCP 等部分底层代码用于共享运行时兼容，不表示当前产品开放这些功能。`gateway/`、`tui_gateway/` 与 `hermes_cli/web_server*` 继续服务 Desktop。后续业务能力通过独立插件与技能实现。

## 主题与运营目标

直接在对话中输入主题、受众、目标和渠道；尚未确定时，可让助手提出少量候选，由用户选择或自定义。系统不预设行业，也不假定用户拥有 App 或处于某个经营阶段。

当前主题通过对话提供；独立主题选择页、模板保存及结构化运营档案属于 MVP 待开发范围。主题是任务上下文，变更通过新消息追加，不重写历史或在会话中途重建系统提示词。修改发行版默认提示词需重启运行时并新建会话生效。

## 本地开发

需要 macOS、Git 和 Xcode Command Line Tools。在本仓库根目录操作，先使用独立开发数据目录：

```bash
export HERMES_HOME="$HOME/hermes-operations-dev"
export HERMES_RUNTIME_DIR="$HERMES_HOME/tools"
source ./activate
npm ci
HERMES_DESKTOP_HERMES_ROOT="$PWD" npm run dev --workspace apps/desktop
```

`activate` 通过 PM 准备工具链；`npm ci` 安装仓库工作区依赖。Node/npm 版本以根目录 `package.json` 的 `engines` 为准。重新进入开发终端时，使用相同的开发目录并重新激活。

Desktop 通过 `hermes gateway ensure --json` 获取或启动本地共享 Gateway，无需另外启动 `hermes serve` 或浏览器 Dashboard。关闭 Desktop 不会停止 Gateway；需要停止时，在同一开发环境执行 `hermes gateway stop`。

临时隔离 Desktop 数据和应用实例可使用：

```bash
scripts/dev-sandbox.sh -- npm run dev --workspace apps/desktop
```

该脚本默认在退出时清理临时数据；需要保留时加 `--persistent`。

## 构建与验证

```bash
npm run typecheck --workspace apps/desktop
npm run test:ui --workspace apps/desktop
```

Python 测试必须使用 `scripts/run_tests.sh`，测试环境见 [贡献指南](CONTRIBUTING.md)；完整静态检查使用 `python scripts/check`。

普通打包与完整运行时打包的区别、macOS 签名和发布验收见 [构建指南](apps/desktop/BUILDING.md)。当前文档不承诺已发布运营版安装包，上游 Hermes 安装包不等同于本分支。

## 文档导航

- [Desktop 使用与开发](apps/desktop/README.md)
- [MVP 方案与验收](docs/operations-platform-mvp.md)
- [开发约束](AGENTS.md)与[贡献指南](CONTRIBUTING.md)
- [平台支持](website/docs/getting-started/platform-support.md)
- [共享运行时参考文档](website/README.md)

共享运行时文档中的跨平台、消息适配器、Kanban 或 MCP 说明描述底层机制，不扩展本运营版的产品范围。

## 许可证

基于 Nous Research 的 Hermes Agent，项目元数据声明为 MIT，见 [pyproject.toml](pyproject.toml)。当前根目录缺少元数据引用的 `LICENSE` 文件，发行前需恢复原始许可证文本。
