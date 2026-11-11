# 当前开发交接记录

## 模型请求详情（2026-11-11）

基准 `803def08b349`；开始时工作树干净。未提交、未重启后台、未调用付费模型或执行真实发布。

- operations 正常/手动/调试模型调用绑定通用的调用观察器，每次物理请求在所属 Profile 的 state.db 保存详情，按已有 call_id 关联 Token，按业务 trace_id 关联重试。插件记录实现位于 model_call_details.py，核心不依赖 operations。
- 私有 `/usage/calls/{id}` 查询原文、参数、解析结果和提供方费用；沿用 Profile 鉴权及业务/主题筛选。执行历史按任务查询全部时间记录，避免旧运行受当天筛选影响。缺失原文或费用明确显示未知。
- Token 用量、执行历史和调试任务均可展开请求详情，重试可逐次查看，按需读取和复制。结构化凭证字段隐藏，图片 Base64 仅留类型和指纹；不改变实际请求。独立生图及主助手尚未接入全文记录，保留原用量展示。
- 验证：标准运行器7文件25项后端测试通过；前端详情/历史入口/趋势/任务页4文件共10项测试通过；修改范围 ESLint、仓库12项检查及 diff 空白检查通过。测试仅使用隔离 Profile 和模拟模型回执，未启动 Desktop 实机或联网调用模型。
- 全局 renderer 类型检查发现基准已有 `browser-toolbar.tsx:33` 的 `back` 未定义（HEAD 同行同样存在）；本轮未修改该文件。首次仓库检查发现既有交接日志路径不符合 no-tmp 规则，已将该日志说明改为相对描述；本轮 lint/复杂度问题已修正。


## State 存储包归并（2026-11-09）

基准 `e187998224`；开始时工作树干净。未提交、未改用户暂存区、未重启后台或访问生产数据库。

- 60 个根目录 `hermes_state*.py` 实现迁至 `state/`：`store.py` 保留 SessionDB/AsyncSessionDB facade，主题模块去掉旧前缀。所有当前消费者、动态导入、patch 路径、子进程片段及对应测试更新；测试归入 `tests/state/`。
- 唯一保留的根 `hermes_state.py` 是旧升级器冻结 ABI 的 SessionDB 导出（9行）；不承载实现，不允许新调用方。未修改 `tests/compat/old_updater_surface.json` 的冻结历史，也未添加其他旧路径转发。
- 包发现纳入 state；更新 CI 路由、源码导航、README 和区域规则。升级/降级检查同时识别历史 `hermes_state*.py` 与新 `state/*.py`，本地 Git 检查和远程树检查均覆盖。协议生成器已重跑，仅源码引用说明变化。
- 50 项 SQL/schema 字符串声明逐项对照未变；用户 state.db 路径、数据及运行规则不迁移。PM lock 检查通过，uv.lock 无需更新。
- 回归：208文件1843通过/64失败/50跳过；在临时导出的原始基准复跑，63项失败相同（主要是 macOS 存储维护测试的既有隔离/平台问题，以及原有 tests/devtools 布局问题）。剩余1项为未跟踪的新文件导致 CI 路径断言失败；完整临时 Git 快照中该套145项全部通过，不改用户索引。
- 消费者回归28文件1640通过/1失败/14错误；唯一断言失败是既有 Nous 模型列表预期，已在基准单独证红。14项错误来自历史源码夹具路径，修复后升级套15项通过；Gateway 新旧树检查4项通过；远程升级/打包后 SQLite 读写57项通过。上述消费者中包含旧升级器冻结兼容564项全部通过。
- 仓库12项检查通过（临时索引识别迁移；0健康规则发现），diff空白检查通过。没有实际启动 Desktop、构建 DMG 或发布内容。临时目录中的 state-* 证据日志仅作本机本轮验证记录。


## Gateway 模块整合（2026-11-09）

基准 `cd5179f4d0`；开始时只有用户的 `.gitignore` 修改，保持原样。未提交、未改用户暂存区、未重启生产后台。

- 原 `tui_gateway/` 已移除，无转发包。共享内容归入 `gateway/rpc/`、`transport/`、`contracts/`、`runtime/`；原 `run_*.py` / `session_*.py` 会话权威保持原位。规则与架构见 `docs/gateway-rpc.md`。
- 同步 Python 导入、内部子进程模块名、源码根定位、包发现、Profile检查、协议生成器、前端说明、技能文档和测试路径；测试迁至 `tests/gateway/rpc/` 与 `tests/gateway/contracts/`。
- 删除旧PTY回连发布器、TeeTransport、终端宠物单元格与journey帧RPC及专用schema。Desktop宠物精灵图、内部stdio、审批、事件回放、Bot/MCP/delegation内部兼容能力保留。
- 保留历史source值、HERMES_TUI_*输入和日志文件名；进程识别同时认识新内部入口及升级前的形态。迁移触发的检查项按现有工具修正了BOM读取与存活探测，未增加配置开关。
- 协议逐项比较：仅删除 `pet.cells` / `learning.frames`，所有保留RPC及schema字段不变；无旧包时新包可独立导入。Desktop完整typecheck通过；PM lock核对通过，uv.lock无需改动。
- 主回归342文件：2814通过、27失败、6错误、11跳过。临时基准检出复跑10个失败文件：680通过、26失败、6错误；唯一新增失败为测试子进程源码根路径，已修正。后续13文件132通过/1跳过，边界6文件89通过；没有新增失败。32项已有失败/错误主要与关闭的访客/连接器/MCP、工具集和语言预期有关，未在此次结构迁移中修改产品行为来适配旧断言。
- 旧终端RPC回归在基准已证红。最终仓库检查使用临时Git索引识别重命名（否则旧大文件被当作新增），不会改动用户索引；最终12项检查通过，diff空白检查通过。


## Evals 目录整理（2026-11-09）

基准 `f59b2e13c8`，开始时工作树干净；保留本轮期间并行写入的其他交接内容。未提交，未运行付费模型或真实浏览器评测，未操作生产 Profile。

- `evals/README.md` 说明运行类型、费用/网络、隔离、覆盖边界和正式测试归属；`CATALOG.md` 索引33个评测族、20个根探针。手动评测均明确标为本轮未完整复跑。
- 产品测试夹具迁到 `tests/agent`、`tests/gateway/fixtures`、`tests/hermes_cli`、`tests/tools`，不保留旧路径转发。产品测试不再导入evals；评测工具自身测试统一归 `tests/evals/`，保留有意的依赖。
- 压缩区域脚本转成2个正式参数化用例；API兼容夹具用有期限的条件等待替换无界sleep轮询。正式Linux进程竞态夹具迁入tests，保留平台标记。
- 移除无正式消费者的Bot Mode、Kanban、公网Webhook、Linux桌面/systemd/旧终端专项探针及过期跨平台workflow模板。delegation/MCP/ACP内部评测保留并标注范围。
- 历史报告集中到 `evals/archive/`：16份文件逐字未变，1份Markdown仅修正归档相对路径。新结果目录保留忽略规则，不覆盖归档。入口导航与文档链接检查通过。
- 验证：17文件55项通过、3项跳过、2项失败；Gateway写入归属失败已在修改前13文件基线复现（49通过/1失败/3跳过）；另一项布局检查发现tests/devtools无对应源码包，HEAD本就有tests/devtools且无devtools/__init__.py，本轮未改该检查或目录。没有为本次整理修改这些产品契约。
- 仓库12项检查通过，diff空白检查通过。使用已有PM测试Python和固定Node26执行，未改依赖。本机临时日志以 `evals-cleanup-` 开头，仅作本轮证据。


## 测试目录分析与发布修复交接（2026-11-09）

- 用户中途切换为分析 `tests/`。本轮静态扫描约6406个Python测试文件、46792个test函数（未展开参数化），其中运营测试约70个；未执行全量测试，也未清理测试文件。工作区仍有并行清理，数量为扫描时快照。
- 发布修复主改动已随工作区推进进入 `856cff2980`；之后的旧索引兼容、预留名额分组及测试变更保留在工作树。此前相关8文件66项、Desktop16项通过，新增旧额度保护后5文件43项通过，完整typecheck通过；未实际重跑发布。
- 发布修复尚未最终收尾：需继续核对 `service.retry_action` 的旧COUNT计数与新的 `publication_reservation_id` 是否一致，避免重试同一预留名额时把前一次安全失败重复计入额度；不要把新批次的通过用例当作原动作重试路径已全部覆盖。
- 测试维护观察：`tests/AGENTS.md` 仍引用已不存在的 `windows-venv-e2e.yml` 工作流；运营公共夹具有从其他test文件导入的情况，可集中到support或局部conftest。`tests/gateway/rpc` 覆盖Desktop通信后端，不能随终端UI移除。


## Nix 桌面范围清理（2026-11-09）

基准 `856cff2980`；此前 Gateway/Docker 等工作已在当前基准中。保留运营发布重试的已有及并行修改；本轮未提交、未启动或重启后台。

- Flake 仅声明 `aarch64-darwin`；删除 NixOS 模块、Linux systemd/容器部署、ELF 修补、Wayland/XDG 启动配置与 Linux 专用运行测试。
- 删除 messaging 包变体以及钉钉/飞书/Matrix 的预装依赖；保留 macOS Desktop、管理命令、终端工具、开发沙箱和 Home Manager launchd。
- `.envrc` 不再观察已删除的终端/网站包；开发提示明确启动 `hermes desktop`。Nix CI 的构建工作移至 macOS ARM runner，缓存按系统/架构分开。
- 保留配置合并、Python 锁、入口与资产检查；增加 macOS launchd/profile 和退役消息配置不激活的 Nix 检查。配置键导出 `packages.configKeys` 保留。
- 验证：发布图、CI 分类、桌面入口与退役平台共199项通过；仓库12项检查通过。使用已有 PM 测试环境经 `scripts/run_tests.sh` 执行（自动环境同步下载 KittenTTS 返回504）。
- 限制：本机没有 Nix，未运行真实 `nix flake check` 或构建桌面包。临时 Tree-sitter 解析器在兼容处理其不支持的参数尾逗号后，19个Nix文件语法检查通过；这不等同于 Nix 求值或构建。


## Docker 镜像发行退役（2026-11-09）

基准 `16aa70604c`；保留工作树中 Gateway、采集设置、运营发布等已有/并行改动，未提交或重启后台。

- 删除 `docker/`、根 Dockerfile/Compose/镜像专用配置、镜像构建/发布/检查工作流、镜像发布模块和专用测试。
- Stable 发布、CI 分类、工作流依赖图与重跑入口不再引用镜像任务，也不再登录 Docker Hub、读取镜像摘要或推动镜像标签。
- 新发布声明 revision 3 拒绝 docker/docker-tests；旧声明与回执仍可读取，尚未发布的旧镜像声明明确要求重新创建桌面声明，且拒绝发生在 I/O 前。
- Docker 终端执行后端、已有沙箱镜像配置与真实远端后端测试保留；Termux 的独立构建环境未纳入此次镜像发行清理。未实际签名/打包/发布应用。
- 验证：发布/CI图/容器后端等累计 448 个不同用例通过，8 项按环境跳过；最后定向复跑 4 项通过，发布排序排除旧 Store 用例后 30 项通过。`scripts/check --base HEAD` 12 项通过；本次路径 `git diff --check` 通过。
- 已知基线问题：5 项 Store 发布用例仍按已退役 Windows/Store 行为断言；另有 PM workflow 的 controller-ref 检查失败，已从 HEAD 导出工作流与原测试到临时目录复现。未为本次清理修改 PM 或 Store 行为。初始 5 文件测试基线为 291 通过/11 失败，本次修正了涉及镜像或当前桌面声明的断言。


## Gateway 旧接入清理（2026-11-09）

基准 `16aa70604c`；开始时已有采集设置、运营发布重试等未提交改动，以及 `gateway/whatsapp_identity.py` 的删除，均保留。未启动/重启后台、未提交、未委派。

- 运行时仅激活 `local`；移除公共 API/Webhook 环境变量启用逻辑和内置外部适配器工厂。
- 删除 MS Graph 接收器、WhatsApp 桥公共模块和对应专用测试；doctor 不再审计退役桥目录。
- 历史身份解析移至 `gateway/session_legacy_identity.py`，修复原文件删除造成的 Gateway 导入失败，保留旧会话标识语义。
- 模型选项解析移至 `gateway/session_model_options.py`，执行路径不再为解析参数导入 API 适配器。
- 部分 API/Webhook 模块仍被共享执行、持久化账本及恢复逻辑引用，保留但不可由运行时激活。边界见 `gateway/platforms/ADDING_A_PLATFORM.md`。
- 验证：累计 133 项不同回归用例通过（入口、历史会话、doctor、桌面私有 API/RPC、模型推理、service tier）；最后两文件复跑 13 项通过。`scripts/check --base HEAD` 12 项通过；未执行整个历史测试集。


## 每日采集额度可选设置（2026-11-09）

该任务开始时基准 `16aa70604c`、工作树干净；以下是采集设置任务记录。当前工作树还含上述 Gateway 及其他运营改动。

### 行为与入口

- 「设置 → 插件 → 自动运营」直接编辑当前业务/主题的采集每日上限；任务计划复用同一 `SourceLimitField`。
- 提供100、200、300、500、1000、2000、3000、5000、10000次/天。保留已有值，不在打开界面时改写；历史低值显示当前值提示，不成为新额度选择范围。
- `/collection-budget` GET返回规则版本、当前主题额度/日期/已用次数、Profile共享额度/日期/已用次数及有效剩余量；PUT仅接受100–10000的整数并通过现有Store.configure做CAS保存。
- 保存不清空当天用量、不发起批次；规则版本更新仍遵循既有暂停旧规则任务与取消排队动作机制。减少上限后如已用量超过新值，剩余量为0。
- 单一活动主题按既有规则同步共享额度；多主题不自动扩大共享限额，界面明确显示约束，其他主题不被改写。
- 前端继承WorkspacePage的连接/Profile/业务/主题归属；后端沿用私有API鉴权与scope_dependency。

### 验证

- Python：collection_settings、collection_policy共7项通过，含真实私有HTTP鉴权/外部主题拒绝、上下界和非整数拒绝、旧版本冲突、用量保留、多主题隔离。
- Desktop：collection-settings、configuration-choices、plan-editor共8项通过；检查真实下拉选择、明确保存才写入、不发起任务、历史值不被渲染时重置。
- 完整typecheck、修改文件ESLint、仓库12项检查通过；README、运行参考与代码地图已更新。

### 运行边界

没有更改生产中已保存的额度，没有启动或重启后台。加载新接口前，待后台空闲后，在同一激活环境和HERMES_HOME执行 `./.hermes/bin/hermes gateway stop` 并等待完成，再启动Gateway。用户选择数值并保存后才生效。
=======
## 小红书运营网页发布入口与返回导航（2026-11-09）

基准 `c6e70eacc5`；开始时工作树干净。用户要求底部“＋”进入网页版发布入口。
此前交接内容对应旧阶段，见基准版本历史；本轮不重跑旧任务，不重启 Gateway。

## 已实现

- `apps/desktop/src/plugins/operations/publish-entry.ts` 提供 guest 内自包含点击适配。
- 仅在 `https://www.xiaohongshu.com` 文档接管 `.publish-btn` 或指向创作者 `/publish/publish` 的链接。
- 仅处理真实主键点击，无修饰键；进入固定 HTTPS 创作者发布地址，沿用原 guest/账号分区。
- 文档级捕获支持后渲染入口、嵌套图标点击、重复安装去重；不处理程序点击或创作者页面最终发布按钮。
- `use-operations-guest.ts` 在每个 dom-ready 安装，失败显示错误；不开放 allowpopups、不打开系统浏览器。
- 代码导航已补充入口，旧 worker 测试补齐真实 webview 所具有的 executeJavaScript 方法。
- 用户反馈进入发布页后无法返回；BrowserToolbar 新增“返回上一页”和“返回首页”。
- Worker 和其他平台页都先完成 takeOver，再调用当前 guest 的历史返回或首页导航；不重建账号分区。
- 无历史记录时返回所属平台首页，失败显示可见错误。新按钮不提交帖子、不解除已有暂停。

## 验证

- 新增 guest 安装合同在原实现上失败；实现后测试执行序列化脚本并验证导航结果。
- 返回按钮合同在新增按钮前失败；实现后覆盖先取得接管、原 guest/分区保留、无历史回首页和错误反馈。
- 最终 4 文件 21 项 UI 测试通过（入口、guest 生命周期、worker、人工接管）。
- Desktop 全量 typecheck、修改文件 ESLint 通过，git diff --check 通过。
- scripts/check 未完成：系统 Python 3.9 不满足要求；改用既有 PM Python 3.14 后缺少固定版本 ruff 0.15.22。

## 验收限制

Computer Use 读取 Electron 窗口长时间未返回，被用户中断，未取得真实 DOM。
用户已反馈能够进入发布页，但工具未完成真实平台 DOM 验证。新增返回按钮仍待实机验收。
开发端加载本轮代码后可在运营画面顶部使用返回按钮；没有历史时返回当前平台首页。
没有真实上传、发布、发消息，也没有修改计划授权或账号状态。
