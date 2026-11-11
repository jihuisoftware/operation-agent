# 开发与 macOS 桌面打包

[返回产品首页](../README.md)

下面面向从源码运行、参与开发或打包应用的读者。已有应用包的普通用户可以直接使用上面的操作指南。

### 本地开发

需要 macOS、Git 和 Xcode Command Line Tools。在仓库根目录运行；两个终端使用相同的数据目录。

**终端一：先停止已有后台服务，再启动。每次启动都按这个顺序执行。**

```bash
export HERMES_HOME="$HOME/hermes-operations-dev"
export HERMES_RUNTIME_DIR="$HERMES_HOME/tools"
source ./activate
./.hermes/bin/hermes gateway stop
./.hermes/bin/hermes gateway run -v
```

**终端二：启动桌面端。**

```bash
export HERMES_HOME="$HOME/hermes-operations-dev"
export HERMES_RUNTIME_DIR="$HERMES_HOME/tools"
source ./activate
npm ci # 首次运行或依赖变化时执行
HERMES_DESKTOP_HERMES_ROOT="$PWD" npm run dev --workspace apps/desktop
```

首次使用独立数据目录，需要重新配置模型提供方；其他配置空间的凭证不会自动继承。环境、连接、调试、Token 解析开关与完整命令见[产品与运行参考](../docs/operations-reference.md#本地开发)。

### 可选的 Nix 环境

Nix 配置仅面向 Apple Silicon macOS：`nix develop` 提供开发环境，`nix build .#desktop` 构建桌面包；也保留 Home Manager 的 macOS 安装与可选 launchd 服务。普通开发仍按上面的 PM 流程进行。

不再提供 messaging 包变体、旧终端聊天入口、Linux 构建目标、NixOS/systemd 或容器部署模块。终端工具、桌面 Gateway 与管理命令继续保留。

### 验证与构建

```bash
# 仓库阻断性静态检查
python scripts/check

# Desktop 类型与界面测试
npm run typecheck --workspace apps/desktop
npm run test:ui --workspace apps/desktop

# Python 测试统一使用仓库运行器
scripts/run_tests.sh tests/plugins/test_operations_debug.py -q

# 当前桌面构建的外壳测试包，不准备新的 Python 运行时，也不上传
npm run dist:mac --workspace apps/desktop -- --publish never
```

Python 测试需要独立测试环境。完整运行时安装包、签名、公证与发布准备见[构建指南](../apps/desktop/BUILDING.md)；详细命令见[发布命令](../docs/operations-reference.md#发布命令)。开发阶段不维护旧运营数据库兼容，升级前请核对数据格式说明。

### 打包并分发 macOS 应用

本仓库不再构建或发布 Hermes Docker 镜像及沙箱镜像。Docker 终端后端仍可使用已有镜像；桌面打包和更新无需 Docker Hub 凭证。

本项目仅提供 macOS 桌面应用。终端聊天前端 `ui-tui`、`hermes --tui` / `--cli` 和“在终端中打开会话”已移除；完整包只装入桌面界面及共享后台。共享后端已统一到 `gateway/`：`rpc/` 处理辅助请求，`transport/` 负责通信，`contracts/` 定义协议，`runtime/` 提供共享运行环境；管理命令和非交互批处理保留。

共享会话存储集中在 [`state/`](../state/)：`store.py` 提供 `SessionDB`，其余模块负责消息、检索、用量、数据库迁移和恢复。Agent、Gateway 和管理命令共同使用这一层，测试位于 `tests/state/`。用户的 `state.db` 路径和内容不受源码目录调整影响；根目录 `hermes_state.py` 仅保留旧升级器需要的 `SessionDB` 兼容入口。

发给没有开发环境的用户，请选择 **`bundled` 完整包**：它同时包含 Electron 界面、Python 后台、锁定的依赖及托管工具，用户安装后不必再执行 `npm run dev`。模型服务仍需用户自行配置或登录。发行包不包含源码专属的“任务调试”页面，普通用户通过内容审核和排期操作。

**本机一键入口**

[打包脚本](../scripts/package_desktop.py)将本机架构、Python、Xcode、发行仓库和签名身份保存在 `.desktop-packaging/config.json`，并生成 `.desktop-packaging/package.sh`。整个本机目录以及 `.p12`、`.pfx`、`.p8` 文件均已加入 `.gitignore`；共享脚本保留在源码中，密码和私钥不写进配置。

首次在一台 Mac 上配置时，用 Python 3.11+ 执行一次；已配置的机器无需重复初始化：

```bash
python3 scripts/package_desktop.py init
```

以后在仓库根目录使用：

```bash
# 只检查环境、工作区和本机配置，不构建
.desktop-packaging/package.sh check

# 完整测试包：核对并提交源码改动后执行
.desktop-packaging/package.sh build
```

默认选择本机原生架构和 `bundled` 完整包，产物在 `apps/desktop/release/`。脚本不会自动提交、创建标签或上传发行安装包；构建会清理旧构建输出。Python 或 Xcode 路径变化时，更新本机配置及入口脚本。自动更新地址需另行配置，不能把打包成功当作更新服务已经可用。

正式签名需要先把含私钥的 **Developer ID Application** 证书导入登录钥匙串；只有 Apple Development 证书时无法完成分发签名。准备好证书后执行：

```bash
# 选择分发证书，并由Apple工具交互保存公证凭据到钥匙串
.desktop-packaging/package.sh setup-signing

# 先在源码中设置实际发行版本，并创建指向当前HEAD的同版本标签
# v0.1.0仅为示例；check不会创建标签或提交软件
.desktop-packaging/package.sh check --signed --tag v0.1.0
.desktop-packaging/package.sh build --signed --tag v0.1.0
```

签名模式会先核对证书、公证凭据、版本和标签，再调用现有完整构建器；构建后验证 `.app` 的签名、Gatekeeper 和公证票据。缺少凭据时停止，不会降级成未签名包。没有分发证书时，可以先使用普通 `build` 验证完整测试包；安装与更新仍按下文验收。

| 构建方式 | 适用场景 | 是否包含完整本地后台 |
| --- | --- | --- |
| `npm run dist:mac --workspace apps/desktop -- --publish never` | 开发时检查当前界面和打包外壳 | 不会重新准备运行时，不作为完整分发流程 |
| `scripts/build-bundle.sh` | 本机完整安装包测试 | 是，默认 `bundled`；本地脚本不做 Apple 公证 |
| `python3 scripts/bundles/desktop.py --tag vX.Y.Z --variant bundled` | 带签名、公证的版本构建 | 是；需先准备版本、证书和公证凭据 |
| `--variant light` | 连接已有远程后台的轻量客户端 | 否，不适合普通用户在本机运行运营任务 |

**1．准备构建环境与发行信息**

- 在 macOS 构建。当前支持 Apple Silicon 的 `arm64` 和 Intel 的 `x64`；应用配置的最低系统版本为 macOS 13。
- 安装 Git、可用的 **Python 3.11+** 和 Xcode 开发工具。完整构建器会准备锁定版本的 Python、Node、npm 等，不要求另行手工安装这些运行时依赖；签名、公证还需可用的 `codesign`、`notarytool` 和 `stapler`。
- 在对应架构的 Mac 或原生 CI runner 上分别构建、验收。当前完整构建器根据构建环境选择目标，不要直接加 `--x64` 或 `--arm64`，让 Electron 与 Python 运行时混用不同架构。
- 所有命令都在仓库根目录运行。构建打包已提交的 `HEAD`，**工作区必须干净，未提交修改不会作为发行内容**。

先检查工具：

```bash
git --version
python3 --version
xcode-select -p
xcrun --find clang

# 正式签名、公证还需通过下面两项
xcrun --find notarytool
xcrun --find stapler
```

如果系统 `python3` 低于 3.11，先切换到满足要求的 Python；本机测试脚本会尝试选择符合版本要求的 `python3` 或 `python`。

打包前核对以下文件。正式发行需确认版本、品牌与更新地址。完成源码修改后提交：

| 文件或设置 | 要确认的内容 |
| --- | --- |
| [pyproject.toml](../pyproject.toml) | 当前版本为 `0.0.0`；发行前改为实际版本，例如 `0.1.0`。稳定标签需与它一致，桌面产物版本由完整构建器注入 |
| [product-identity.cjs](../apps/desktop/product-identity.cjs) | 核对 `bundled` 的显示名称、应用标识和安装身份，并确认用户数据目录是否需要与上游版本隔离。当前完整包默认名仍为 **`Hermes Agent`**，修改开发环境的应用名不会自动改掉它 |
| [electron-builder.config.cjs](../apps/desktop/electron-builder.config.cjs) | 核对图标、协议、打包资源和更新配置；使用本项目自己的发行身份 |
| `GITHUB_REPOSITORY`、`CLOUDFLARE_R2_PUBLIC_URL` | 使用自己的发行仓库和更新服务，不能把运营版的更新交给上游 Hermes。完整更新管线另见下文 |
| 根目录 [LICENSE](../LICENSE) | 已恢复项目原始 MIT 许可证；发行时保留版权声明及第三方许可说明 |

不要把开发 Profile、数据库、API Key、网站登录数据或签名私钥提交进源码。安装后的用户数据保存在应用包外，不能把开发机的数据目录当作运行时载荷复制给用户。

**2．先生成完整的本机测试包**

```bash
# 此命令应无输出；先核对并提交需要打包的改动
git status --short

# 完整构建当前提交，不需要创建标签或推送代码
scripts/build-bundle.sh
```

产物位于 `apps/desktop/release/`，包括当前架构的 **DMG、ZIP 和应用目录**，具体名称以构建输出为准。DMG 供用户下载后安装，ZIP 也是后续更新管线需要的产物。

本地脚本会清理上一次构建输出、复用依赖缓存，并清除用于正式签名公证的环境变量。它生成的是验证完整运行时的测试包，**不是正式公证发行包**；即使系统钥匙串中的证书参与了部分二进制签名，也不能据此视为已完成公证。

**3．准备签名与公证，构建正式版本**

需要自己的 Apple Developer 账号，以及包含私钥的 **Developer ID Application** 证书。将导出的 `.p12` 放在源码仓库外；公证凭据可以使用钥匙串配置，或通过 CI 注入 App Store Connect API Key。Apple 的机制说明见[签名与公证文档](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)。

下面使用“`.p12` 签名证书＋钥匙串公证凭据”。`v0.1.0` 和证书路径均为示例，按实际发行版本替换。凭据初始化命令请逐条执行，完成交互提示后再继续：

```bash
# 交互式保存公证凭据到钥匙串；按提示输入账号、团队及应用专用密码
xcrun notarytool store-credentials "operations-notary"

export CSC_LINK="/absolute/path/DeveloperID.p12"

# 输入证书密码，输入不回显；不要把真实密码写进 README 或提交到仓库
read -r -s CSC_KEY_PASSWORD
export CSC_KEY_PASSWORD

export APPLE_NOTARY_PROFILE="operations-notary"
unset CSC_IDENTITY_AUTO_DISCOVERY
export GITHUB_REPOSITORY="your-org/your-repository"

# 先提交版本和发行配置，确认工作区干净；标签必须指向当前 HEAD
git status --short
git tag v0.1.0

# 直接调用完整构建器；不要用会清除签名凭据的 build-bundle.sh
python3 scripts/bundles/desktop.py --tag v0.1.0 --variant bundled --clean
```

也可以用 `APPLE_API_KEY`（`.p8` 文件路径）、`APPLE_API_KEY_ID`、`APPLE_API_ISSUER` 替代 `APPLE_NOTARY_PROFILE`。现有 CI 使用 Secret `APPLE_API_KEY_P8` 写出密钥文件，再交给公证钩子；CI 中直接注入签名变量，不执行上面的交互式 `read`。不要把密钥内容写入构建命令或项目文件。

完整构建会准备运行时并构建 Electron，签署应用及嵌套二进制，再由 [notarize.mjs](../apps/desktop/scripts/notarize.mjs) 提交 Apple 公证并将票据附加到 `.app`。**公证凭据未配置完整时，钩子可能跳过公证；仅出现“打包成功”不代表可以正式分发。** 应核对日志中的 `Accepted` 和票据附加结果。

构建器默认不会上传应用安装包或更新频道。公证会把待公证软件提交给 Apple；向用户分发或上传自己的发布站点是后续步骤。

**4．验证产物，再发给用户**

将下面路径替换成实际生成的 `.app` 路径。若改了产品名称，应用文件名也会变化：

```bash
RELEASE_APP="apps/desktop/release/mac-arm64/你的应用名.app"

codesign --verify --deep --strict --verbose=2 "$RELEASE_APP"
spctl --assess --type execute --verbose=4 "$RELEASE_APP"
xcrun stapler validate "$RELEASE_APP"
```

如果分发流程还需要给 **DMG 本身**附加公证票据，可以在生成最终 DMG 后执行：

```bash
RELEASE_DMG="apps/desktop/release/实际安装包名称.dmg"
xcrun notarytool submit "$RELEASE_DMG" --keychain-profile "$APPLE_NOTARY_PROFILE" --wait
xcrun stapler staple "$RELEASE_DMG"
xcrun stapler validate "$RELEASE_DMG"
```

ZIP 分发的是其中已经签名并附加票据的 `.app`，不要对 ZIP 执行 `stapler`。签名后不要修改包内源码、依赖或资源；改动后应重新构建、签名和验证。

在另一台同架构 Mac 或干净用户环境完成实际验收：

1. 退出开发版，停止旧后台，再安装并启动测试应用，避免旧开发环境掩盖运行时缺失。
2. 双击 DMG，将应用拖入「应用程序」，从 Finder 启动；无需打开终端、Vite 或手工运行 Python 后台。
3. 配置模型，验证聊天、资料读取、生成待审图文和登录状态持久化；发布验收另选明确授权的测试稿件。
4. 退出再打开应用，确认用户数据仍在，且没有连接到开发目录或依赖源码仓库。
5. 分别记录版本、提交 SHA、架构、签名身份及验收结果，再将对应 DMG 分发给用户。

**5．需要自动更新时，再接入发行管线**

自动更新还需要自有更新地址、匹配的 DMG/ZIP、更新清单以及真实的旧版→新版安装测试。只上传一个 DMG 不等于完成自动更新。

- 先核对 [.github/workflows/desktop-bundled-release.yml](../.github/workflows/desktop-bundled-release.yml)、[稳定版构建流程](../.github/workflows/stable-release.yml)和[稳定版发布流程](../.github/workflows/stable-release-publication.yml)中的仓库、存储地址、权限与 Secrets。
- 本项目已有 R2/更新频道管线；使用自己的 `CLOUDFLARE_R2_PUBLIC_URL`、存储桶和相关凭据，并按该流程发布产物与更新清单。仅设置 `GITHUB_REPOSITORY` 不代表 macOS 更新链路已经配置完成。
- 原生更新验收使用实际签名包，验证旧版安装、应用内更新、自动重新启动和用户数据保留，参见[安装与更新验收](../tests/install/BUNDLED_UPDATES.md)。
- `--commit` 构建适合独立试用，自动发行频道更新被关闭，应用身份带提交后缀；不要把它当成稳定版本的长期升级路线。

当前 README 描述的是构建与验收方法，不表示本运营分支已经产出通过全部分发验收的正式安装包。更细的准备/构建分离、缓存和版本规则见 [Desktop 构建指南](../apps/desktop/BUILDING.md)。

### 文档导航

| 文档 | 适合什么时候看 |
| --- | --- |
| [产品与运行参考](../docs/operations-reference.md) | 查功能细节、额度、执行边界、调试与完整启动命令 |
| [运营插件说明](../plugins/operations/README.md) | 查运营规则、数据保存、接口和恢复方式 |
| [功能代码导航](../docs/code-map.md) | 按功能定位实现与测试 |
| [研发评测入口](../evals/README.md) · [专项索引](../evals/CATALOG.md) | 能力/成本评测、运行条件与历史结果边界 |
| [开发工作流](../docs/development-workflow.md) · [当前交接](../docs/dev-handoff.md) | 继续已有任务、核对改动与验证范围 |
| [Desktop 文档](../apps/desktop/README.md) · [构建指南](../apps/desktop/BUILDING.md) | 桌面连接、排错、打包与更新 |
| [开发约束](../AGENTS.md) · [贡献指南](../CONTRIBUTING.md) · [测试指南](../tests/AGENTS.md) | 开始修改代码前查阅 |

### 项目来源与许可证

基于 Nous Research 的 Hermes Agent，遵循 [MIT 许可证](../LICENSE)，元数据见 [pyproject.toml](../pyproject.toml)。独立技能与第三方依赖遵循各自的许可证。
