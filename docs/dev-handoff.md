# 当前开发交接记录

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
