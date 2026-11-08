# 当前开发交接记录

## 独立写稿页与富文本草稿（2026-11-08）

基准 `c29ba91d14`，本轮开始已有未提交的封面模板/候选编辑改动，全部保留；写稿改动也未提交。未委派代理。行为与使用说明见 [writing-editor.md](writing-editor.md)，入口见 [code-map.md](code-map.md)。

### 实现

- 内容新增“写作草稿”，手动写稿和编辑旧稿统一进入静态 `/content/write?draft=<id>`。沿用连接、Profile、业务、主题归属；切换归属清除旧稿参数。
- Tiptap 开源扩展统一精确锁定 3.32.0；标题、加粗/斜体/下划线/高亮、列表、引用、链接、代码、表格、素材 ID 图片、拖动、剪贴板、本地上传、撤销重做。MIT 及新增编辑器依赖的许可汇总已保留并纳入 Desktop public 分发目录，无 Cloud/付费扩展或新后台进程。
- `writing/controller.ts` nanostore 串行保存，2 秒防抖、Cmd+S；回执只更新修订号，不替换文档。请求结果不明时复用原请求 ID，网络失败有界退避；400 校验失败允许修改后新请求，409 保留本地稿并提供另存/载入服务器版本。
- `writing/journal.ts` IndexedDB 恢复副本按连接、Profile、业务、主题、稿件、窗口隔离；SDK 通用 Profile 缓存生命周期通知驱动重命名/删除。初始化新稿需后台可用，已有稿离线可恢复。
- `writing_drafts.py` 独立可变工作稿：标题 200 字、正文 10 万字符、JSON 2 MiB。私有 CRUD/复制/归档/预览/提交 API，CAS 修订及幂等请求；列表仅返回摘要。
- `writing_document.py` 白名单文档验证、纯文本投影、封面优先图片去重，前后端共用 JSON 样例。外链图片以惰性模板解析为待导入占位，既不抓取也不允许未处理占位提交。
- `writing_submission.py` 显式提交冻结富文本快照和原发布字段；同修订并发提交只生成一份待审稿，后续版本保留根/父关联。人工审核排期沿用原流程；自动保存不调用模型、不建立发布授权或迁移旧排期。
- 全新手稿可声明原创；AI 派生稿由服务器继承来源、分析依据及权限。素材/来源变化在提交时复查，原稿不被覆盖。
- CoverStudio 适配工作草稿，选封面只保存工作稿；正式富文本稿换封面保留文档及正文图片。无图提交沿用本地文字封面。
- `image-drag.ts` 直接移动封闭的图片节点，修复 Chromium 从表格内拖图携带表格上下文、导致嵌套表格的问题。

### 验证

- Python：writing 8、content_review 10、content_versions 4、cover_design 9，共 31 项通过；最后版本关联修改后 writing 8 项再次通过。
- Desktop：writing/controller/projection、content-library、content-review、cover-studio、section-page、SDK，共 39 项通过。
- macOS 真实 Electron 隔离验收通过：Chromium IME 中文组合输入、格式/表格、撤销重做、图片上传/拖动/外链粘贴、离线重开同步、真实 IndexedDB 多窗口/连接/Profile 重命名删除、10 万字符编辑保存。只用模拟 API/临时用户目录；未使用生产账号。系统输入法候选词选择未人工验收。
- 可重跑：`npm run test:writing-native --workspace apps/desktop`。最后截图在系统临时目录 `operations-writing-native-6KfTRw/writing.png`；已检查主题布局。长文测量为隔离模拟 API，不代表真实后台端到端延迟。
- 完整类型检查、修改文件 ESLint、仓库 12 项检查和 `git diff --check` 均通过。
- npm audit 无 Tiptap 告警；报告中的既有构建/运行依赖告警未在本轮批量升级。

### 保留的封面工作

四种本地模板、四套配色、三候选缓存、中文字体测量/换行、独立封面文案与原质检、手动版本及排期约束均保留；前一轮封面布局和来源回归结果见相关测试。本轮没有回退已完成修改。

### 运行边界

未重启生产后台或桌面，未改真实稿件、审核、排期或发布。加载新接口须待后台空闲后先停止再启动；桌面需重新加载新依赖与页面。没有自动重跑业务链路。
