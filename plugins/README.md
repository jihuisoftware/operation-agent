# 运营版内置插件范围

`plugins/` 保存实际实现，`plugin-catalog/` 保存外部插件的安装记录；两者都不表示所有能力默认启用。

## 保留能力

- `operations/`：运营业务、主题与计划、资料采集、内容生产、网页执行、数据分析及台账。
- `model-providers/`、`web/`、`browser/`、`image_gen/`、`video_gen/`：模型、检索、浏览器和媒体后端。
- `dashboard_auth/`、`memory/`、`context_engine/`、`cron_providers/`：认证、记忆、上下文和调度扩展。
- `plugin_loader.py`、`plugin_storage.py`、`plugin_utils.py`：公共插件基础设施。
- `disk-cleanup/`、`security-guidance/`：按需启用的清理和文件安全提示。
- `delegation/`、`computer_use/`：产品已禁用的共享底层，按根开发约束保留。
- `kanban/dashboard/plugin_api.py`：共享 API 兼容实现及测试保留；本版不分发其界面清单，
  不因保留代码而开放看板。

本轮移除 `google_meet/`、`hermes-achievements/`，以及 Kanban 的 Dashboard 清单、前端构建产物
和独立 systemd 单元。相应专属测试与使用说明同步清理；用户数据和账号配置未删除。
`memory/byterover/`、`memory/retaindb/` 仍保留，不能在迁移目标尚未就绪时直接删除。

## 外部插件目录筛选

规则位于 `hermes_cli/data/operations-profile.json` 的 `pluginCatalog`，实现位于
`hermes_cli/plugin_catalog_scope.py`。在本地或在线目录解析完成后，对浏览、搜索、首次推荐
以及模型的目录搜索结果统一筛选：

- 按执行插件的后台宿主系统展示兼容或未限定平台的条目；消息平台类不展示。
- 保留模型、记忆、检索网页、语音四类后端，另明确列出内容、素材、办公及营销插件。
- 对退役功能使用显式排除；未知桌面、工具或自动化条目不会因上游新增而自动进入推荐。
- 已安装条目仍可在管理结果中查看。按名称安装、深链接查询、更新、迁移和安全封禁
  使用完整目录；此规则是产品发现范围，不是新的安装黑名单。

目录展示数量随宿主系统及目录版本变化；远程后台的插件兼容性按后台宿主判断，不按桌面客户端系统猜测。
未删除目录 YAML 或改变 `removed.yaml`，避免影响固定版本更新、安装来源验证和旧配置迁移。
此规则不修改上游网站，也不改变已经开始的会话工具集或提示缓存。
