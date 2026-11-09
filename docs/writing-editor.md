# 独立写稿与工作草稿

内容 → 写作草稿 → 手动写稿打开 `/content/write?draft=<id>`。标题、正文、图片、封面和来源在同一工作稿中编辑。停止输入两秒自动保存，也可按 Cmd+S；只有“提交审核”才生成正式待审版本。审核、排期与发布仍使用原流程。

- 支持标题层级、粗体、斜体、下划线、高亮、列表、引用、链接、代码块、简单表格和图片拖动。
- 上传、拖放和粘贴本地图片意味着确认有使用权限。外链图片不自动抓取，显示待导入占位；未处理占位不能提交。
- 工作稿允许标题 200 字、正文 10 万字符、JSON 2 MiB；发布仍受当前通道标题 20 字、正文 900 字、图片 18 张限制。超长稿可另存副本后精简，系统不截断全文。
- 发布预览是纯文本投影，标题和代码按文本保留，列表加编号或圆点，表格按行以 ` | ` 分隔，链接附 URL；字体、颜色等不原样发布。封面优先，其余图片按正文顺序去重。
- 全新手稿可明确声明原创；AI 派生稿保留服务端依据和权限校验。原创声明不授予发布权限，也不等于自动质量检查通过。
- 自动保存失败显示“仅本机暂存”。恢复网络或点击保存重试。恢复副本存入 IndexedDB，按连接、Profile、业务、主题、稿件及窗口隔离；Profile 重命名/删除跟随处理。多窗口修订冲突保留本机稿，可另存副本或显式放弃本机修改后载入服务器版本。
- 创建新工作稿及从正式稿初始化需要后台可用；已打开过的工作稿可从本机恢复副本继续编辑。正式版本、排期及历史正文始终不被自动保存覆盖。

## 实现与开源许可

编辑器采用 [Tiptap](https://github.com/ueberdosis/tiptap) 3.32.0 开源扩展，版本精确锁定；交互参考 [Simple Editor](https://tiptap.dev/docs/ui-components/templates/simple-editor)。界面使用本项目组件与主题，没有接入 Tiptap Cloud 或付费扩展，没有增加后台进程。编辑器依赖的 [第三方许可汇总](../apps/desktop/public/licenses/writing-editor.txt) 随桌面应用分发。MIT 许可原文见 [tiptap-MIT.txt](../apps/desktop/public/licenses/tiptap-MIT.txt)。

前端：`apps/desktop/src/plugins/operations/writing/`；后端：`plugins/operations/writing_*.py`。私有接口位于 `/content/writing-drafts`，共用原连接、Profile、主题鉴权。更新使用修订号 CAS，所有变更带幂等请求 ID。列表不返回大文档，详情按需加载。保存、预览和提交不调用模型；无图时提交沿用本地文字封面。

## 按需生成组图

写稿页可展开“生成杂志组图”，生成后明确应用整套配图，保留正文和表格。模型调用只发生在点击生成或检查时，自动保存不生图。详见 [组图样张与费用说明](visual-generation.md)。

## 本机验收

`npm run test:writing-native --workspace apps/desktop` 构建隔离页面，以临时 Electron 用户目录和模拟 API 验证中文组合输入、格式、表格、保存及离线恢复，并输出截图位置。不使用生产账号或后台。这里验证 Chromium 的 IME 组合事件；实际 macOS 输入法候选词选择仍建议由使用者体验确认。
