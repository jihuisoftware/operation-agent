# 研发评测与复现入口

`evals/` 用于能力、成本、性能对比和专项故障复现，不参与桌面运行，也不打进应用包。普通行为回归在 `tests/`；不要批量执行本目录，也不要把脚本存在、旧报告或本地模拟通过当作当前版本验收。

## 先选运行类型

| 类型 | 用途 | 模型费用/外部访问 | 隔离与产物 |
|---|---|---|---|
| 正式回归 | 持续验证运行时契约或评测工具本身 | 本次选定用例使用模拟模型；不调用付费推理 | `scripts/run_tests.sh` 管理临时数据、环境与进程 |
| 离线分析/本地模拟 | 读取副本、计算指标、模拟协议与故障 | 通常无推理费用；本地 HTTP、子进程或浏览器仍可能启动 | 只用数据库/日志副本，输出到临时目录 |
| 真实模型 A/B | 比较准确率、Token、缓存、耗时 | 会使用配置中的提供方凭据并产生费用；浏览器/云端运行还会访问外部服务 | 明确模型、任务数量、重复次数、基准/候选 SHA 和输出目录 |
| 待复核专项探针 | 保存仍有潜在价值的一次性复现方法 | 未逐项核验，不能假定无费用或无副作用 | 先读源码与局部 README；尤其检查顶层代码、固定路径、凭据读取和进程清理 |

开发/测试环境使用根目录 [CONTRIBUTING.md](../CONTRIBUTING.md) 与 [开发规则](../AGENTS.md) 的 PM 流程。不要把旧 README 中的直接 pip/uv 安装命令用于 Hermes 托管环境。原生 Electron 探针另外需要锁定的 Node/npm 依赖和实际 macOS Electron 二进制。

真实评测前选独立 `HERMES_HOME`，显式传入输出路径；需要历史状态时使用副本。不要使用生产 `state.db`，也不要把 shell 中的所有凭据无差别传给子进程。`--help` 不保证无副作用：部分旧脚本有顶层执行代码，先读入口。

## 当前关注的评测族

“保留”代表与当前产品相关，不代表本轮已重跑。以下手动评测最后一次完整验证的当前版本/系统均为**未知**；历史验证只以报告记录的 SHA、日期和平台为准。

| 评测族 | 目的与入口 | 运行条件/费用 | 结果与覆盖边界 |
|---|---|---|---|
| [compaction](compaction/README.md) | 压缩后的事实召回；`python evals/compaction/runner.py --transcript COPY.json --out OUT` | 项目环境、会话副本、已配置辅助模型；生成问题/压缩/评分可能付费 | `OUT` 下报告；召回质量不等于完整长期任务成功率 |
| [readtool](readtool/README.md) | 大文件、异常文件读取效果；`runner.py --model MODEL --provider PROVIDER --label LABEL` | 真实模型；临时文件夹具；可能付费 | 本地 `results/`；比较正确率、调用数和Token，不代替所有文件安全测试 |
| [browser_use](browser_use/README.md) | 浏览器路径 A/B；按局部说明指定两个源码树运行 `orchestrate.py` | 模型、浏览器及外部网站；可能有推理和云浏览器费用 | `--results` 指定 JSONL；仅覆盖任务集，网站变化会影响结果 |
| [reasoning_replay](reasoning_replay/README.md) | 各提供方 reasoning 重放；`harness.py run ...` / `report --out OUT` | 真实提供方凭据；可能付费 | `OUT` 的矩阵与调用成本；需逐路由核对证据 |
| [prefix_rediet](prefix_rediet/README.md)、[token_accounting](token_accounting/) | 固定提示词、缓存与用量变化 | 混合模拟与真实调用；按具体入口核验 | 保留原始用量与缓存字段；估算值不能当实际账单 |
| [session_search_schema](session_search_schema/README.md) | 会话检索接口对任务效果的影响；`runner.py --base REF --cand REF --model MODEL` | 基准/候选源码、模型凭据；可能付费 | 本地结果与报告；历史 PR95570 结果已归档 |
| [shared_gateway](shared_gateway/README.md) | 启动、Profile、只读查询和验收回执 | 本地隔离进程；已实现驱动各自有覆盖边界 | 完整统一驱动仍未实现；场景清单不是通过证明 |
| [desktop_gateway_ticket_native](desktop_gateway_ticket_native/README.md) | macOS Electron main 的票据与多 Profile 连接 | 真 Electron、本地临时 Gateway；模拟模型，无推理费用 | receipt 与进程日志；不是完整 renderer/UI 验收 |
| [desktop_bug_campaign](desktop_bug_campaign/)、[desktop-pane-fixture](desktop-pane-fixture/README.md) | 滚动、Markdown、会话状态与加载时序复现 | 具体入口需要前端构建/本地服务；尚未逐项复跑 | 局部 UI/状态证据；注入时序不等于真实负载复现 |
| [postmortem](postmortem/README.md) | 成本、缓存、工具和任务运行复盘 | `forensics/` 读取副本、不请求模型；`live_ab/` 按入口判断 | 区分 OBSERVED 与 MODELED；报告覆盖率和缺失日志 |

其余脚本见 [完整目录索引](CATALOG.md)。工具发现、delegation、MCP、ACP 的用户入口可能关闭，但内部契约仍存在，所以保留为专项研究/兼容验证，不用这些评测恢复产品功能。

## 正式测试与夹具归属

产品测试不再从 `evals/` 导入夹具；只有 `tests/evals/` 直接测试评测工具本身。需要持续门禁的行为放进对应产品测试目录，手动探针可以反向复用夹具；不保留旧路径转发文件。

| 契约 | 正式测试 | 夹具/实现位置 |
|---|---|---|
| 推理响应结构 | `tests/agent/test_reasoning_shape_boundaries.py` | `tests/agent/reasoning_shapes.py` |
| 心跳执行归属 | `tests/gateway/test_heartbeat_{acceptance,execution_ownership}.py` | `tests/gateway/fixtures/heartbeat_wire.py`；手动 runner 仍在本目录 |
| API 内部交付契约 | `tests/gateway/test_api_delegation_delivery_contract.py` | `tests/gateway/fixtures/api_delegation.py`；不代表公网 API 已启用 |
| Gateway 写入归属 | `tests/gateway/test_failure_writer_ownership.py` | `tests/gateway/fixtures/failure_ownership_probe.py` 与相邻独立写入进程 |
| 完成通知批处理 | `tests/hermes_cli/test_completion_backlog.py` | `tests/hermes_cli/completion_backlog_probe.py` |
| MCP device flow | `tests/tools/test_mcp_device_flow.py` | `tests/tools/mcp_device_flow.py` |
| 进程超时竞态 | `tests/agent/test_deadline_fork_race.py` | `tests/agent/fixtures/cron_timeout_fork_race.py`；Linux 原生契约，macOS 跳过 |
| 压缩区域边界 | `tests/agent/test_compaction_region_scoping.py` | 本文件夹具；模拟辅助模型 |
| 评测/取证工具自身 | `tests/evals/` | 工具仍在 `evals/`，依赖方向有意保留 |

例如：

```sh
scripts/run_tests.sh tests/evals/ tests/agent/test_reasoning_shape_boundaries.py tests/agent/test_compaction_region_scoping.py
```

## 历史材料和新增规则

历史结论与数据集中到 [archive/](archive/README.md)。新输出写评测自己的 `results/` 或显式目录；不要覆写归档，不提交私有会话、密钥或个人日志。

新增评测必须在本索引或对应目录说明：目的、命令与依赖、费用/网络、数据与进程归属、输出、覆盖限制，以及最后实际验证的 SHA/系统。未运行就标“未知”；一次性专项脚本先进入待复核目录索引，验证稳定后再决定是否转为正式回归。
