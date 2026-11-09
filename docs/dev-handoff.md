# 当前开发交接记录

## 采集规则误停兼容修复（2026-11-09）

- 本轮保留全部未提交的杂志组图改动。新增默认 `image_mode` 暴露了采集预留阶段的旧配置兼容缺口：`Store.policy()` 补默认值，而 `collection_ledger.reserve()` 在事务内比较原始 JSON，导致旧主题未改规则也报“运营规则变更，停止采集”。
- 修复事务内比较，采用与 `Store.policy()` 相同的默认值合并；不写回配置、不改变规则版本，不取消真正的规则变化或暂停保护。
- 旧配置缺 `image_mode` 用例修复前复现失败；缺 `brand` 的同类用例也在未修改基准 `7ba2354132` 临时副本中复现。修复后采集及新增兼容/竞争条件回归共10项通过，仓库12项检查通过。
- 未重启生产后台、未重跑真实采集。需空闲后在同一环境/HERMES_HOME先执行 `./.hermes/bin/hermes gateway stop` 并等待完成，再启动后台加载修复。


## 杂志组图与生图恢复（2026-11-09）

基准 `7ba2354132`；开始时工作树干净，独立写稿及旧封面功能已提交。本轮组图改动尚未提交，未委派代理。用户确认：清爽杂志与信息图，通常 3–6 页，最多两张 AI 主视觉＋全篇一次额外尝试；自动稿自动生成，手写稿按按钮生成。

### 已实现

- 自动内容生产默认 `image_mode=magazine`；设置中可明确选 `basic` 保留原本地文字封面。生图失败不降级冒充完成，正文先保存为草稿。
- `visual_plan` 受限分页与完整文案；`visual_render` 1080×1440 杂志封面、流程、对比及要点页，中文由 Pillow 精确绘制，先排版校验再付费生图；正文主要字号提高到42像素。
- `visual_provider` 复用已配置的生图路由，不切换失败供应商；外层360秒超时。输出进入当前Profile缓存及授权素材库，不增加核心工具或常驻进程。
- `visual_sets` 逐页、逐插画持久化，按提示和提供方配置复用主视觉；跨重试及自动修订保留三次尝试上限。结果不明不会在定时重跑时重发，需手动重试。
- `visual_job_state` 执行代次、幂等请求、后台重启中断检测；后台复制请求Context，绑定Profile、秘密及业务归属。取消后的迟到结果不能继续应用；重做失败可恢复上一套，保留费用记录。
- `visual_review` 使用辅助视觉模型检查实际组图，按完整图片组合缓存通过记录；所有页的文字纳入原事实检查。视觉失败不会用文字重写掩盖；人工审核与发布授权仍独立。
- `image_gen/usage_receipts.py` 为非聊天消费者收集供应商已有用量回执；运营图片调用进入同归属Token账本和日报，未知费用/Token不按零处理。
- 私有 `/visual-sets` API：创建、状态、取消、恢复及显式应用；复用草稿CAS或正式稿指纹。手写稿整套替换配图，保留正文和表格；正式稿创建新待审版本，旧排期不迁移。
- Desktop「杂志组图」支持逐页预览、原图、重试、单页主视觉重做、恢复上一套和整套应用。自动保存不调用生图。

### 实际样张

[样张与使用说明](visual-generation.md) 包含封面、流程页、对比页、主视觉和完整提示词；资产位于 `docs/assets/visual-samples/`，均压缩到500KiB以下。主视觉用内置imagegen生成，本地项目代码完成中文排版。样张不是通过用户生产生图账号生成，也未发布。

### 验证

- 相关Python11文件68项通过：visuals、blueprints、prompt_inputs、recovery_gaps、source_library、content_review、content_versions、content_autorepair、writing、model_budget、model_failures。
- 日报调用计数补充回归：visuals 11项与report_summary 3项通过，相关独立测试合计71项；图片调用纳入总调用数，Token回执按独立图像阶段展示。
- Desktop 6文件20项通过：image-studio、writing/controller/projection、content-library、cover-studio、plan-editor；完整typecheck及修改文件ESLint通过。
- `npm run test:writing-native --workspace apps/desktop` 在临时macOS Electron用户目录及模拟API下通过：真实组图界面、整套替换、正文/表格保留、不触发审核发布，以及既有中文组合输入、拖图、离线恢复、多窗口/Profile隔离和10万字保存。截图位于系统临时目录 `operations-writing-native-FYUtww/writing.png`。
- 仓库12项检查、差异检查通过。相关旧测试显式选择basic，保留原文字封面、来源与修订合同；新用例覆盖默认magazine全链路。
- 扩展供应商回归132项通过、1项既有失败：`tests/plugins/image_gen/test_openrouter_compat_provider.py::TestImageApiSurface::test_catalog_models_are_offered_only_by_openrouter`，缺少目录项 `x-ai/grok-imagine-image-quality`。已在未修改HEAD的临时git archive中用官方runner复现；本轮未改该目录逻辑。

### 运行边界

未停止或启动生产Gateway、未调用生产生图账号、未改真实稿件或发布。实际使用需配置生图及视觉模型；图片效果仍取决于所选模型。加载新后台前，必须在同一激活环境和HERMES_HOME执行 `./.hermes/bin/hermes gateway stop` 并等待完成，再启动Gateway；不自动重跑生产任务。
