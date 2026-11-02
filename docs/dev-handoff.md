# 当前开发交接记录

记录日期：2026-11-02；基于 `89d6644e24`。工作树包含此前 APP 改版、节省 Token 和本轮多业务改版，大量文件已由外部暂存；本轮未重置索引或提交。恢复时核对 HEAD、暂存区和实际 diff。本文是证据，不授权外部动作。

## 本轮并行完成：可选技能目录裁剪

`optional-skills/` 从 152 项裁剪为 57 项，删除 95 项及其专属脚本、模板和参考资料。
完整去留清单与理由见 `optional-skills/README.md`。保留内容、媒体、检索、表格、演示、
分析和电商能力；删除训练研发、代码委派、链上支付、游戏、健康设备、家居及退役产品技能。
`mcporter` 是独立按需 CLI，保留不等于启用内置 MCP；远程上游安装机制保持不变。

同步去除关联技能推荐，删除 10 个只覆盖已移除实现的测试文件，保留共用测试中的有效用例。
运行 `website/scripts/generate-skill-docs.py` 更新英文目录、技能页及侧栏，清理中文镜像和目录，
修复引用与安装示例；生成器也补齐既有小红书技能的目录入口。网站无链接指向本次删除的技能页。
未触及用户已安装技能、配置、凭证或核心运行时，不执行真实账号操作。

验证：`scripts/run_tests.sh tests/skills tests/website tests/tools/test_skills_hub.py`，
30 文件、1145 项通过、2 项按 Windows 平台跳过。覆盖作者规范、资源、文档与安装源行为。
`python scripts/check --base HEAD` 十二项通过，差异空白检查通过。
日志：`tmp/operations-acceptance/optional-skills-20261102/`。上轮 MCP 清理仍保留 27 项，见 `optional-mcps/README.md`。

## 本轮：多业务、多主题

已实现 Profile → 业务空间 → 主题 → 独立计划。业务类型是默认配置分类，名称可修改，归属使用稳定 ID。侧栏支持选择、搜索、新建、复制配置、改名、暂停、归档及明确关联账号；首页有当前业务/全部业务汇总。页面及通知标注归属，记录链接解析原主题，跨 Profile 切换清除旧范围参数，迟到响应不覆盖新页面。

- 存储采用 Profile 内 `workspaces.db` 目录与共享台账、`data.db` 原计划、`topics/<ID>.db` 独立主题 SQLite，避免旧服务直接 SQL 遗漏过滤。ownership 表与 JSON 触发器保存并索引业务/主题归属，私有 HTTP、CLI、调试显式绑定范围；旧无范围接口固定映射原计划。
- 原有一个 Cron 扫描主题，按阶段轮转；手动请求按 `(topic_id, request_id)` 持久化去重，普通排期队列每阶段只保留最后一次到期项。各主题保持本地租约、快速首轮上限及阶段顺序。全局/业务/主题暂停和账号接管相互独立。
- 每业务独立账号槽与 Cookie 分区，原账号保留原分区散列。Desktop 按账号维护后台网页，切换业务、主题或隐藏不卸载；收到的命令按其原归属写步骤与回执。共享账号统一租约、额度、消息认领和结果不明状态；重复扫码要求明确关联，待处理消息可转交而不自动发送。
- Profile 采集/模型总额沿用原规则，按原时区日界统计；主题更低额度继续有效。素材、品牌与知识在业务内共享，归档规则保持只读；公开来源可明确跨主题引用，保留图片及出处，不跨业务引用内部资料或绕过数据集公开权限。
- 迁移前备份 `before-workspaces.db`，根据规则版本、原主题和执行关系拆分归属；不确定记录进入归档历史待归属。原库与目录使用 SQLite super-journal 提交，迁移失败阻止新主题执行；历史人工归属只建立带规则快照的关联，不重放动作、不退还消耗。
- 入口见 `docs/code-map.md` 及 `plugins/operations/README.md`。`workspace_broker.py` 管理账号轮转/心跳/通知/接管；`workspace_topics.py` 管理新主题默认值、改名和来源引用；`workspace_history.py`、`workspace_inbox.py` 管理人工归属及转交。

## 验证

仅使用临时 Profile、模拟模型和模拟网页；未调用真实账号、未发布互动、未重启用户的 Server/Desktop，也未用 computer use。

- 后端运营回归：31 文件 156 项通过。新测试覆盖同名隔离、跨范围私有接口/素材访问、迁移重试与备份、共享预算、登录登记、并发账号领取、重复扫码、接管、手动幂等、素材引用、知识共享和归档只读。
- `test_operations_workspace_pipeline.py` 使用真实业务服务，模拟两个业务、每业务两个主题，完成采集→整理→数据/行业分析→选题→内容→发布及互动→日报；验证分析引用、20 条模拟外部动作、记录归属及请求重试。
- Desktop：30 文件 103 项通过；包括不可变请求归属、迟到响应、未保存切换提示、跨 Profile URL、后台网页持续执行及回写原主题。类型检查和本轮修改范围 ESLint 通过。
- `python scripts/check` 十二项通过；收尾队列回归 5 文件 25 项通过，补充迁移中断/账号限制测试后该文件 8 项通过，最终 Ruff 与差异检查通过。日志保存到 `tmp/operations-acceptance/workspaces-20261102/`（忽略目录）。
- Python 必须通过 `scripts/run_tests.sh`，测试解释器为 `/Users/dm/.hermes/installs/c8c5bff47822afc6/test-environment/gen-c848a0c51e694f03b964753d4a5ef4c9/venv/bin/python`。仓库检查把 `/opt/homebrew/bin` 及该解释器目录加入 PATH，避免系统 Node 12；未用 pip/uv 修改环境。

## 保留的既有工作与使用边界

此前六主入口、首页快速开始、20 条/3 查询的持久化首轮、就绪恢复边界、统一计划设置、旧 URL、独立网页接管均保留。节省 Token 设置仍按 Profile 保存 `token_saving.enabled/parse_images/parse_files`；不会重写已有上下文或中途切换工具集。此前 Token 专项验证记录位于 `tmp/operations-acceptance/token-saving-20261102/`。

部署后重启 Server 和 Desktop 才会加载新私有接口及执行器。现有开发 Profile 的真实数据库尚未升级，升级在首次访问时完成。模拟与组件测试通过不等于实际 Electron 多窗口、休眠恢复或真实平台已验收；本轮没有新增真实发布授权。账号冲突须关联原账号或切回原登录身份，不能靠重复扫码重置额度。
