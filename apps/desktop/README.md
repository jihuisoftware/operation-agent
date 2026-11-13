# 通用运营 Desktop

本分支提供通用运营能力，主题由用户自行输入或选择，首批渠道为公众号、小红书和抖音。**macOS 已支持，Windows x64 恢复中（原生验收待完成）；界面固定为简体中文**。旧语言设置会归一到中文，不提供语言切换。产品范围见[根 README](../../README.md)，业务模块进度见 [MVP 方案](../../docs/operations-platform-mvp.md)。

应用图标采用深蓝底、浅色对话气泡与青绿色增长箭头。矢量源为 `assets/operations-mark.svg`，通过根目录的 `scripts/generate-icons.mjs` 生成 Dock、ICNS、macOS 26 分层图标及界面品牌素材；保持现有深浅色和系统单色适配。替换图标资源后重启 Desktop 可更新开发版 Dock，已安装版本需重新构建安装包。

## 输入或选择主题

在输入框说明本次运营的主题、受众、目标和渠道；方向未确定时，可请助手提供候选，再选择或自定义。已有上下文会继续使用，无需每次重新填写。当前使用对话入口，独立主题选择与保存界面仍待开发。

## 当前能力

Desktop 提供流式对话、工具执行展示、内容预览、文件浏览、模型与凭证配置、技能、记忆和定时任务。语音、图像和视频相关能力取决于所配置的模型与服务。

右上角的地球图标「显示浏览实时画面」直接显示右侧内嵌网页。地址栏、登录和网页交互都在面板内完成；智能体通过 `desktop_preview` 与 `drive_preview` 操作同一页面。再次切换按钮会隐藏或恢复当前页面，不重新打开系统浏览器。独立浏览器与云端页面不共享这里的登录状态；更新后新会话采用面板浏览指引，旧会话可明确要求使用上述工具。

Bot Mode、Kanban／Radio 界面及旧的 agents、starmap、webhooks、session-import 页面已移除。多 Agent 协作工具、Kanban 工具与自动派单、MCP 服务及公共 API／Webhook 当前关闭。素材台账、内容审批、发布回填和增长报表仍待开发，生成草稿不代表已经发布。

## 本地开发

Server 与 Desktop 分别在两个终端启动，均从仓库根目录运行，使用相同的开发数据目录。

终端一先停止已有 Server（Gateway），再启动；每次启动都执行停止步骤：

```bash
export HERMES_HOME="$HOME/hermes-operations-dev"
export HERMES_RUNTIME_DIR="$HERMES_HOME/tools"
source ./activate
hermes gateway stop
hermes gateway run -v
```

等 Server 启动完成后，在终端二启动 Desktop：

```bash
export HERMES_HOME="$HOME/hermes-operations-dev"
export HERMES_RUNTIME_DIR="$HERMES_HOME/tools"
source ./activate
npm ci # 首次运行或依赖变更后执行
HERMES_DESKTOP_HERMES_ROOT="$PWD" npm run dev --workspace apps/desktop
```

Desktop 自动发现现有 Gateway，无需手动填写后端端口；`5174` 是 Vite 开发服务端口。当前连接逻辑在 Gateway 不存在时仍会自动启动后端。若已有后台 Gateway，先退出 Desktop，再在相同开发环境执行 `hermes gateway stop`，然后启动前台 Server。结束调试时先退出 Desktop，再在 Server 终端按 `Ctrl+C`。

macOS 源码构建需要 Git 和 Xcode Command Line Tools。Node/npm 版本以根目录 `package.json` 的 `engines` 为准；依赖从仓库根目录安装，关联 Desktop、共享组件与 TUI 等工作区。

源码启动优先使用所选仓库的 PM 启动器，由 PM 配对 Python 与依赖环境；显式设置 `HERMES_DESKTOP_PYTHON` 时保留该解释器选择。启动器不可用或指向其他工作副本时，启动会报告错误，需在当前仓库重新执行 `source ./activate`。不要用残留的旧 `venv` 搭配另一 Python 版本的依赖目录。

已准备好本分支运行时的开发环境也可执行 `hermes desktop`。不要把上游安装器或上游公开安装包当成本运营分支的发行物。

使用独立的 Desktop 数据目录与应用实例：

```bash
scripts/dev-sandbox.sh -- npm run dev --workspace apps/desktop
scripts/dev-sandbox.sh --persistent -- npm run dev --workspace apps/desktop
```

第一条命令退出时清理临时数据；第二条保留数据供下次启动。启动界面调试可运行 `npm run dev:fake-boot --workspace apps/desktop`。

## 运行边界

- **Electron**：解析后端运行时，管理原生窗口、文件系统、Git、安装与更新，通过受限 preload 接口提供原生能力。
- **React**：管理路由、面板、交互状态和对话展示；共享状态按功能放入 nanostores。
- **Gateway 与 Agent**：管理会话、模型调用、工具执行与调度，通过 `gateway.rpc` 的 JSON-RPC／WebSocket 和共享 HTTP API 服务 Desktop。

本地连接通过 `hermes gateway ensure --json` 获取或启动共享 Gateway，使用私有控制票据认证。无需独立启动 `hermes serve`，也不使用浏览器 Dashboard 前端。退出 Desktop 或切换连接只断开查看端，不终止 Gateway；需要停止时执行 `hermes gateway stop`。

`gateway/`、`gateway/rpc/`、`apps/shared/` 与 `hermes_cli/web_server*` 是 Desktop 的依赖。保留这些组件不表示重新开放消息机器人或公共 Web 界面。

Bundled 构建使用包内运行时，数据留在包外。包内运行时损坏时应报告损坏，不自动改用任意 PATH 上的 Python 或 Hermes。源码构建可通过 `HERMES_DESKTOP_HERMES_ROOT` 指向明确的工作副本。

## 连接与 Profile

现有本地、远程及 Cloud 连接机制保留。使用远程连接时，Agent 工具、终端和文件操作在远程后端执行。共享连接机制不代表本分支承诺支持其他桌面操作系统；远程后端兼容性需单独验证。

Profile 用于隔离配置、凭证、历史和业务数据。连接或 Profile 切换只改变当前查看与请求路由，不应取消后台任务。项目可以组织多个目录和会话；业务台账仍须由后续业务插件持久化。

## 截图快捷键

在设置中启用截图快捷键后，同时按左右 Command 键可截取当前应用的前台窗口，并作为附件加入最近活动的输入框，不会自动发送。此功能默认关闭，需要 macOS 的输入监控及屏幕录制权限。授权后按系统提示重启应用，再检查附件内容。

## 构建与更新

从仓库根目录执行：

```bash
npm run pack --workspace apps/desktop       # 未封装的应用目录
npm run dist:mac --workspace apps/desktop   # DMG / ZIP
scripts/build-bundle.sh                    # 完整运行时包，要求干净工作区
```

普通 `pack`／`dist:mac` 不会准备一份全新的 Agent 运行时。完整构建、arm64／x64 目标、签名与公证要求见 [BUILDING.md](BUILDING.md)。本分支不提供 Windows/Linux 打包命令。

macOS bundled 应用使用包所属的更新渠道与 `electron-updater`；源码安装使用源码更新流程。`hermes update` 不重写 bundled payload。更新前确认目标仓库、分支和渠道属于当前运营版，安装包是否可用以实际构建产物为准。

## 验证与排错

```bash
npm run typecheck --workspace apps/desktop
npm run lint --workspace apps/desktop
npm run test:ui --workspace apps/desktop
npm run test:desktop:platforms --workspace apps/desktop
```

安装、启动、更新或打包路径变更还应执行 `npm run test:desktop:all --workspace apps/desktop`，并完成实际 macOS 安装包验证。仅类型检查或单元测试通过不代表发布验收完成。

启动失败先检查当前 Profile 数据目录下的 `logs/desktop.log`，再核对运行时路径、模型配置与 Gateway 状态。使用 PM 的诊断与修复路径，不直接删除正在使用的运行环境。macOS 麦克风权限需要重置时可执行：

```bash
tccutil reset Microphone com.nousresearch.hermes
```

修改代码前阅读 [AGENTS.md](AGENTS.md)、[src/AGENTS.md](src/AGENTS.md) 和 [DESIGN.md](DESIGN.md)。许可证状态见[根 README](../../README.md#许可证)。

Windows 开发、测试包与原生验收入口见[Windows 恢复使用说明](../../docs/windows-development.md)。
