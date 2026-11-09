# 历史评测归档

这里保存过去评测留下的对照数据，不是当前版本验收记录。源码、模型、提供方行为及价格可能已经变化；只能引用记录中实际注明的日期和版本，缺失的来源信息视为未知。

| 来源 | 记录 | 保留目的 |
|---|---|---|
| compaction | [压缩结果](compaction/results/) | 2026-08-15 / 2026-09-19 的压缩召回与循环结果，解释历史取舍 |
| session_search_schema | [PR95570](session_search_schema/results/pr95570/) | 会话搜索 schema 调整的模型对比 |
| core_tool_deferral | [结论](core_tool_deferral/results/SUMMARY.md) | 工具延迟暴露的历史对比 |
| readtool | [结论](readtool/results/SUMMARY.md) | 文件读取工具的历史对比 |

原运行器继续写各自的 `results/` 或显式输出路径；新运行结果不会覆盖这里。复跑必须使用自己的临时目录，记录代码 SHA、模型/提供方、配置和实际系统。不要提交真实会话全文、凭据或个人日志。
