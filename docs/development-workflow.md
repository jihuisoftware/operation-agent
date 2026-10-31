# 控制开发上下文的工作流

根 [AGENTS.md](../AGENTS.md) 和区域指引是规则来源。本页提供按需使用的方法；产品使用说明在 [README](../README.md)，功能定位在 [代码导航](code-map.md)。

## 开始一项任务

1. 明确本次可验收结果、影响功能和当前用户约束。先看 `git status --short`，识别已有未提交修改。
2. 选择代码导航中的相关入口，读取适用的 AGENTS。已经在当前上下文中完整读过且未变化的规则无需反复读取。
3. 用符号或用户看到的文案定位实现，再读函数及邻近逻辑。遇到边界问题，沿调用方、接口契约和测试扩展范围。
4. 恢复旧任务时核对交接记录的基准提交和工作树。记录与代码不同，以当前证据和用户最新要求为准。

```bash
# 先看有哪些相关文件，再找定义与调用
rg --files plugins/operations apps/desktop/src/plugins/operations
rg -n 'def (preview|apply)|/blueprints/apply' plugins/operations apps/desktop/src/plugins/operations
# 按搜索结果调整范围，避免输出整个大文件
sed -n '75,130p' plugins/operations/blueprints.py
```

搜索范围从功能目录开始，必要时扩大到全仓。入口文件较大时先查函数名或 import；测试先找相关用例。锁文件、生成代码、构建产物和超大日志只在对应问题需要时读取。固定行号仅用于当次定位，不写成长期接口契约。

## 实现与验证

保持一次改动可独立验收；遇到与目标无关的重构，记录候选并另行处理。新行为放在职责明确的模块中，沿用现有 API 和规则服务。需要拆分大文件时，先覆盖行为契约，再移动代码、更新调用及文档。

按变更选择验证范围。例如运营蓝图需要：

```bash
# 使用 CONTRIBUTING.md 规定的独立 Python 测试环境；如有需要设置 HERMES_PYTHON
scripts/run_tests.sh tests/plugins/test_operations.py tests/plugins/test_operations_http.py tests/plugins/test_operations_workflow.py tests/plugins/test_operations_blueprints.py
npm run test:ui --workspace apps/desktop -- src/app/cron src/plugins/operations
npm run typecheck --workspace apps/desktop
python scripts/check --base HEAD
```

日志较长时，将完整输出重定向到临时文件并保留进程退出码。先读汇总和失败位置，再读相关堆栈；缺失信息时扩大读取，不能把截断后的输出当作完整证据。通过的测试只汇报范围、结果和必要限制。前端失败中的整页 DOM 不要反复输出；日志可能包含敏感资料，不纳入版本库。

检查通过后，只有新的修改、失败或未解决疑点才需要扩大或重跑验证。纯导航和规则文档改动检查链接、指令一致性及仓库检查，无需重跑业务测试。

## 交接记录

[docs/dev-handoff.md](dev-handoff.md) 保存当前任务快照，建议控制在约 80 行内。完成一个可验收阶段、切换任务或交接时更新；替换过期状态，长期设计决定放在所属模块文档。不要保存聊天全文、完整 diff、原始日志、凭证或真实账号资料。

记录以下信息即可：

- 目标、状态、记录日期、基准提交；是否存在尚未提交的相关改动。
- 当前范围、用户约束及需要保留的已有修改。
- 关键入口与已实现行为，链接到代码导航或模块文档。
- 验证命令、结果、运行范围；明确哪些是上一阶段结果、哪些检查尚未执行。
- 未解决问题和下一步。未获授权的外部动作不能因为交接记录中出现就执行。

新会话的恢复提示可写为：

> 继续处理「具体任务」。先核对 docs/dev-handoff.md 和当前工作树，按 docs/code-map.md 定位相关模块，再读取适用的 AGENTS。沿用已确认约束，从剩余事项继续。

交接记录帮助恢复工作，但不会扩大执行权限，也不保证旧测试结果适用于新改动。较大需求分成多个可验收阶段，完成后再开始下一阶段，避免把长期项目的全部历史放进同一次开发会话。
