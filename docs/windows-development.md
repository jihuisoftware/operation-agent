# Windows x64 开发与测试包

当前状态：已恢复 Windows x64 的源码准入、MSIX 构建与辅助验收入口，**尚未完成 Windows 原生构建、安装、签名及升级验收**。macOS 原有流程保留。恢复范围及未完成条件见[恢复计划](windows-desktop-recovery-plan.md)。

按本轮确认，暂沿用仓库已有产品身份、MSIX Publisher 和更新配置；没有自动上传产物或更新正式渠道。正式对外分发前，再确认发行身份与签名凭据是否属于本项目。

## 开发运行

开发机需要 Windows x64、Git for Windows，以及运行当前开发工具所需的环境。现有 `setup-hermes.sh` 识别 Git Bash 的 Windows 宿主，PM 管理实际运行依赖；不要使用 raw pip/uv 改动托管环境。

在 **Git Bash** 中，两个终端使用相同的开发数据目录：

```bash
export HERMES_HOME="$(cygpath -am "$LOCALAPPDATA")/hermes-operations-dev"
export HERMES_RUNTIME_DIR="$HERMES_HOME/tools"
source ./activate
```

终端一：使用该环境的 `hermes` 管理命令，先停止再运行后台：

```bash
hermes gateway stop
hermes gateway run -v
```

终端二：

```bash
npm ci
HERMES_DESKTOP_HERMES_ROOT="$(cygpath -am "$PWD")" npm run dev --workspace apps/desktop
```

首次使用独立数据目录，需要配置模型和业务账号。不要把正式数据目录用于安装和恢复测试。开发环境命令本身仍需在 Windows 原生机器上验收，不能将 macOS 上通过的参数测试当作 Windows 启动证明。

## 完整测试包

在 Windows PowerShell 中运行；建议使用 PowerShell 7。构建需要 Git、Python 3.11+ x64，以及依赖编译所需的原生工具。构建器通过 PM 准备锁定的 Node、Python、依赖和打包工具。

构建内容来自已提交的 `HEAD`，工作树必须干净。本轮修改尚未提交时，构建器会拒绝打包，不会悄悄打出旧代码。

```powershell
# 仅准备依赖和原生工具
./scripts/build-bundle.ps1 -PrepareOnly

# 完整本地测试包；忽略调用者签名凭据，不发布
./scripts/build-bundle.ps1

# 已配置原有 Windows 签名凭据时显式选择；失败不会退化成未签名包
./scripts/build-bundle.ps1 -Signed
```

默认产物在 `apps/desktop/release/`：Windows x64 MSIX 和 `win-unpacked/`。未签名 MSIX 是测试产物，不能作为已完成签名的安装包分发。脚本不会替用户安装或信任证书。

`npm run dist:win --workspace apps/desktop` 是 Electron 打包入口，需要已有完整载荷；普通开发者应优先使用上面的完整构建器，避免误把界面外壳当作完整安装包。

Windows ARM64、ia32、Linux 桌面及 Windows light/Store 变体不属于本轮恢复范围。Windows 安装包必须在 Windows 原生构建，不能从 macOS 冒充 Windows 目标。

## MSIX 与 AppInstaller

- MSIX 清单保留共享应用数据的虚拟化设置，并为载荷实际声明的管理命令生成独立隐藏入口；不恢复终端聊天 UI。
- Windows SDK、资源编辑工具、Azure 签名配套库及 .NET runtime 由固定版本的打包工具供应并记录校验值，消费阶段验证准备结果。
- Azure 路线继续读取原有 `AZURE_SIGN_*` 与 Azure 凭据；也保留打包器现有证书配置路径。不要将私钥或密码提交到源码。
- 已恢复更新后重启等待脚本资源；保留原有 Windows 更新检查模块。恢复代码不等于完成升级验收。

对已签名的单个 x64 MSIX，可以在本地生成 AppInstaller 描述文件：

```powershell
python scripts/bundles/windows_descriptor.py `
  --package apps/desktop/release/实际安装包.msix `
  --out apps/desktop/release/preview.appinstaller `
  --public-base https://你的下载域名/windows-preview
```

默认生成固定版本描述符，不启用自动更新。明确配置测试更新目录后，使用 `--update-policy automatic` 生成带更新检查的描述符。命令读取包内真实身份与版本，只写本地文件，**不上传、不推进渠道**。签名文件存在性检查不代替 Windows 原生签名验证。

## 原生 CI 与启动验收

手动运行 `.github/workflows/windows-desktop-recovery.yml`。它准备固定工具、隔离测试环境，运行平台与打包契约，按选项构建完整测试包、检查二进制架构并启动解包后的应用。

该工作流仅上传 GitHub 测试产物，不提交 Microsoft Store、不发布正式下载，也不更改更新通道。需要修改进入可运行的远程分支后才能触发；本轮没有自动推送或触发工作流。

本机也可执行：

```powershell
./scripts/windows-desktop-smoke.ps1 -AppDirectory apps/desktop/release/win-unpacked
```

脚本使用独立临时 Profile，先停止该 Profile 的后台，再启动应用；检查窗口及后台进程出现，最后关闭测试进程和后台。它不登录平台、不调用模型、不发布内容。此启动检查不代替完整安装、会话交互、网页发布与更新验收。

原生字体测试要求测试机装有简体中文字体。缺失时应先准备系统字体能力，再完成本地封面验收，不能用跳过该验收宣称配图可用。

## 尚未完成的发布门槛

1. Windows 11 x64 实机安装、卸载、重装和中文路径验证。
2. 中文输入法、字体渲染、素材上传、独立写稿及封面效果验证。
3. 网页执行器心跳、只读登录、睡眠唤醒、历史阻塞隔离与模拟排期发布验证。
4. 使用有效凭据完成 Windows 签名验证，并验证从测试版本 A 升级到 B、失败恢复与用户数据保留。
5. 验收通过后，将 Windows 接入正式发布准入与更新通道。当前正式发布矩阵不因恢复工作自动扩容。

## 历史代码来源

按需恢复原文件，未整体回退历史提交：

- MSIX 清单、工具供应与签名模块：`7a027d320a` 删除前的版本。
- 打包准备记录的 Windows 工具校验、更新重启等待脚本：`cd5c479479` 删除前的版本。
- 已保留原文件的实现与说明；新清单准备模块适配当前完整载荷，未恢复旧 TUI、Copilot 快捷入口或 Store 发布任务。
