# 通用运营平台

基于 Hermes Agent 的运营助手，通过对话协助完成素材整理、选题、内容草稿、排期提醒和复盘。运营主题、品牌、受众与目标由用户定义，首批面向公众号、小红书和抖音，按实际需要选择渠道。

**主要入口为 macOS Desktop，界面仅支持简体中文。** 已加入每日目标驱动的运营插件：来源采集、规则授权、素材与内容版本、后台网页执行、互动台账和日报。模拟整日流程已验证，真实账号与网站兼容性仍待联调。详细任务与验收见 [MVP 方案](docs/operations-platform-mvp.md)。

## 产品范围

| 状态 | 能力 |
| --- | --- |
| 已保留 | Desktop 对话、内容预览、文件处理、检索、浏览器、终端、代码执行、技能、记忆、待办和定时任务 |
| 按配置可用 | 图像理解、图片生成、视频理解、配音；实际可用性取决于模型与服务 |
| 已实现，待真实账号联调 | 小红书网页搜索、笔记与可见评论读取、图片上传请求、图文编辑器填写与回读核验 |
| 已实现，待真实账号验收 | 自动运营工作台、目标与规则、网页/RSS 采集、素材授权与内容版本、图文/互动执行队列、人工接管、指标导入、内容包与日报导出 |
| 后续扩展 | 自动视频、AI 封面、更多平台发布与登录采集适配器、完整指标自动回收 |
| 当前关闭 | 多 Agent 协作工具、Kanban 工具与自动派单、MCP 服务、公共 API／Webhook、自动技能整理、插件自动更新检查 |
| 已移除入口 | Bot Mode、Kanban／Radio 界面、内置消息平台适配器、浏览器 Dashboard 前端、Windows 打包 |

产品范围由 [operations-profile.json](hermes_cli/data/operations-profile.json) 统一定义，后端与 Desktop 共用。旧配置不会重新启用本版已关闭的能力；范围覆盖不改写用户原始配置文件。

`gateway/`、`tui_gateway/` 与 `hermes_cli/web_server*` 继续服务 Desktop。业务能力优先通过技能和独立插件扩展；保留的 delegation、Kanban、MCP 底层代码用于共享运行时兼容，不表示产品已开放这些功能。

### 小红书网页控制

[小红书技能](skills/social-media/xiaohongshu/SKILL.md) 在 Desktop 中使用右侧内嵌网页进行搜索、读取和表单填写，上传文件由用户在面板选择。对于用户明确选择的独立自动化，另提供 `browser_exec` 脚本：

- 打开小红书与创作中心，识别需要登录或人工验证的页面。
- 按关键词搜索，读取笔记正文和当前可见评论，保留来源链接。
- 将指定本地图片交给网页上传框，并填写标题与正文。
- 回读编辑器核对内容，遇到已有不同草稿时停止覆盖。

Desktop 可直接在右侧页面登录，无需额外配置浏览器；独立自动化脚本需要配置可用浏览器。可在新会话中要求：“在右侧实时画面打开小红书，搜索我指定的主题，整理笔记链接和可见内容。”具体调用方式、上传前提与状态说明见技能文档。

当前脚本不执行发布，也不确认草稿已保存到草稿箱。上传请求已发出不等于平台处理完成；读取范围仅限页面可见内容。离线行为测试已通过，真实账号登录、上传处理与当前网站页面兼容性仍需联调。新增技能在同步后通过新会话使用，保持已有会话的提示词缓存稳定。

### 浏览实时画面

点击桌面窗口右上角的地球图标「显示浏览实时画面」，在右侧直接打开网页。这里是可交互的内嵌页面，用户和智能体操作同一页面，支持输入网址、登录、跳转与滚动。

- 在面板地址栏输入网址，或在对话中要求“在右侧实时画面打开小红书”。智能体通过 `desktop_preview` 打开和读取页面，通过 `drive_preview` 操作，不另开系统浏览器。
- 再次点击地球图标可隐藏面板，再打开保留当前网页；页面按会话归属，沿用 Desktop 现有的标签页与配置隔离。
- 独立浏览器或云浏览器中的页面不会自动搬入此面板；它们的登录状态也不共享。需要时在面板内重新登录。文件上传由用户在面板选择文件。
- 更新代码后重启 Server 与 Desktop；新会话采用新的浏览指引。旧会话可明确要求“使用 desktop_preview 在右侧打开网页，使用 drive_preview 操作，不使用独立浏览器”。

## 每日自动运营

进入 **设置 → 插件 → 自动运营**，填写主题、目标、账号、来源、知识和素材，选择允许的动作、额度与时间，然后启用并保存规则。规则范围内自动执行，无需逐条确认；超出范围或结果不明的动作留在待处理记录中。

点击右上角「运营画面」或工作台「查看执行网页／登录」，在内嵌网页登录并查看后台任务。该执行页面独立于当前聊天，按连接与 Profile 隔离登录状态；登录或人工接管会先暂停自动动作，完成后回工作台恢复规则。Mac、Server 和 Desktop 需保持运行。

默认每天 09:00 采集，10:00 发布，11:00 / 15:00 / 19:00 互动，21:00 日报。支持素材授权撤回、内容版本编辑、ZIP 内容包导出、指标导入、异常核对和 Markdown 日报。未知结果不自动重发，缺少素材或来源时允许不发布。

聊天查询与 CLI 需要启用后端插件（同一个已激活的开发环境）：

```bash
./.hermes/bin/hermes plugins enable operations
./.hermes/bin/hermes ops status
./.hermes/bin/hermes ops pause
```

配置和恢复步骤见[运营插件使用说明](plugins/operations/README.md)。现有小红书技能仍用于对话中的浏览和填写；自动发布/互动由运营插件规则和执行台账管理。测试未操作真实账号，当前页面兼容性、消息入口和真实最小化运行仍需授权联调。

## 主题与运营目标

在 Desktop 对话中说明主题、受众、目标、渠道及可用素材即可开始。例如：

> 我想围绕“城市步行”做小红书内容，面向周末出游人群。先根据我提供的照片提出三个选题，再为选中的题目写图文草稿。

> 我还没有确定运营方向。请先了解我的素材和目标，提供几个候选主题，由我选择。

示例主题不作为系统默认值。助手沿用当前任务已确认的信息，缺少真实素材、数据或授权时明确说明；内容草稿、发布建议与实际执行结果分别报告。

可通过对话讨论主题，也可在「设置 → 插件 → 自动运营」保存主题、项目／品牌档案、目标和运营规则。主题变化以新消息追加，不重写历史上下文；不同 Profile 的素材、事实、账号授权和指标不自动混用。

## 本地开发

需要 macOS、Git 和 Xcode Command Line Tools。运行时与开发工具由仓库的 PM 环境准备，Node/npm 版本约束见根目录 [package.json](package.json)。

开发时将 Server（Gateway）和 Desktop 分别放在两个终端运行。以下命令均在仓库根目录执行，两边必须使用相同的 `HERMES_HOME`。

终端一：准备环境并在前台启动 Server，`-v` 将详细运行日志输出到当前终端：

```bash
cd /Users/dm/code/agent/operation-agent &&
export HERMES_HOME="$HOME/hermes-operations-dev" &&
export HERMES_RUNTIME_DIR="$HERMES_HOME/tools" &&
source ./activate &&
./.hermes/bin/hermes gateway run -v
```

等 Server 启动完成后，在终端二启动 Desktop：

```bash
export HERMES_HOME="$HOME/hermes-operations-dev"
export HERMES_RUNTIME_DIR="$HERMES_HOME/tools"
source ./activate
npm ci # 首次运行或依赖变更后执行
HERMES_DESKTOP_HERMES_ROOT="$PWD" npm run dev --workspace apps/desktop
```

`activate` 准备并激活开发环境；`npm ci` 安装整个仓库工作区的前端依赖。重新打开终端时，使用相同的数据目录并再次激活。启动后在 Desktop 中配置模型与凭证；图片、视频等服务按需配置。环境管理细节见 [PM 开发流程](website/docs/reference/package-management.md#developer-workflow)。

首次使用独立数据目录时，模型列表为空是因为尚未配置提供方；其他安装或 Profile 的模型与凭证不会自动继承。在模型选择弹窗点击「添加提供方」，完成登录或填写 API Key，再选择模型。也可以在已激活的开发环境运行 `./.hermes/bin/hermes model` 完成配置，随后重新打开 Desktop 的模型选择器。

「添加提供方」和设置页提供 Kimi、DeepSeek 的直接入口。Kimi 默认进入中国区密钥配置，国际区可在密钥表单中切换；请使用对应区域开放平台的 API Key。保存后选择模型并确认即可使用，模型列表由后端目录提供。凭证申请与接口说明见 [Kimi 中国区](https://platform.kimi.com/docs/api/overview)、[Kimi 国际区](https://platform.kimi.ai/docs/api/overview)和 [DeepSeek](https://api-docs.deepseek.com/zh-cn/)。

也可直接进入「设置 → 模型」，在「提供方」下拉框选择尚未配置的提供方，填写 API Key 并点击「连接」，再选择并应用模型。聊天中的模型选择器只展示已配置提供方的模型。

Desktop 通过 `hermes gateway ensure --json` 发现并连接已运行的 Server，HTTP API 和 WebSocket 均由该 Gateway 提供，无需另外启动 `hermes serve`，也无需手动指定后端端口。`5174` 是 Desktop 的 Vite 开发服务端口。当前 Desktop 在找不到 Gateway 时仍会自动启动后端，并非仅连接模式。

若之前已经由 Desktop 启动了后台 Gateway，先退出 Desktop，在相同开发环境执行以下命令，再执行终端一的前台启动命令：

```bash
hermes gateway stop
```

关闭 Desktop 不会停止 Server。结束调试时，先退出 Desktop，再在 Server 终端按 `Ctrl+C`；也可在相同开发环境执行 `hermes gateway stop`。

需要独立的 Desktop 数据与应用实例时，在已准备好的开发环境中使用：

```bash
scripts/dev-sandbox.sh -- npm run dev --workspace apps/desktop
```

默认退出时清理临时数据；加 `--persistent` 可保留用于后续调试。配置、凭证与历史按 Profile 隔离，行为设置写入 `config.yaml`，密钥写入 `.env`。启动排错与连接说明见 [Desktop 文档](apps/desktop/README.md)。

### 验证改动

```bash
# Desktop 类型、界面与 Electron 测试
npm run typecheck --workspace apps/desktop
npm run test:ui --workspace apps/desktop
npm run test:desktop:platforms --workspace apps/desktop

# 小红书控制脚本与技能规范
scripts/run_tests.sh tests/skills/test_xiaohongshu_skill.py tests/skills/test_authoring_standards.py -q
npm run test --workspace tests-js -- xiaohongshu-page.test.mjs

# 仓库阻断性静态检查
python scripts/check
```

Python 测试统一使用 `scripts/run_tests.sh`，不要直接运行 `pytest`。测试环境与贡献约定见 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [测试指南](tests/AGENTS.md)。涉及安装、更新或打包的改动还需完成对应的 macOS 安装包验证。

## 发布命令

以下命令均在仓库根目录运行。普通桌面打包用于检查当前 UI 和应用外壳，不会准备一份全新的 Agent 运行时：

```bash
# 生成未封装的应用目录，不上传产物
npm run pack --workspace apps/desktop

# 生成 macOS DMG / ZIP，不上传产物
npm run dist:mac --workspace apps/desktop -- --publish never
```

需要包含 Python、Node、Agent 依赖与托管工具的完整本地安装包时，先提交待打包的代码，确保工作区干净，再运行：

```bash
scripts/build-bundle.sh
```

完整构建打包当前 `HEAD`，产物位于 `apps/desktop/release/`。脚本不推送代码、不发布 Release；本地包不经过 Apple 公证，不能代替正式发布验收。

正式分发还需完成目标架构验证、签名、公证、安装与更新验收，并配置当前运营分支自己的发布仓库和更新渠道。完整流程见 [构建指南](apps/desktop/BUILDING.md)；仓库保留的[稳定版发布流程](website/docs/developer-guide/stable-releases.md)描述共享运行时机制，使用前需核对本分支的 CI 与发布配置。上游 Hermes 安装包不等同于本运营版产物。

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [MVP 方案](docs/operations-platform-mvp.md) | 业务模型、分阶段任务、审批与发布状态、验收标准 |
| [小红书技能](skills/social-media/xiaohongshu/SKILL.md) | 网页控制方法、调用示例与已知边界 |
| [Desktop 文档](apps/desktop/README.md) | 桌面开发、连接、Profile 与排错 |
| [构建指南](apps/desktop/BUILDING.md) | 完整运行时包、macOS 签名、公证与发布验收 |
| [开发约束](AGENTS.md)与[贡献指南](CONTRIBUTING.md) | 代码组织、会话缓存、扩展边界与测试要求 |
| [共享运行时文档](website/README.md) | 模型、工具、技能、调度与底层机制参考 |

共享文档中的跨平台、消息适配器、Kanban 或 MCP 说明不扩展本运营版的产品范围。

## 许可证

项目基于 Nous Research 的 Hermes Agent，元数据声明为 MIT，见 [pyproject.toml](pyproject.toml)。当前仓库根目录缺少元数据引用的 `LICENSE` 文件，正式发行前需恢复原始许可证文本。独立技能及第三方依赖的许可证以各自声明为准。
