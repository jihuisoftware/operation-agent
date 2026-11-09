# macOS 原生 Gateway 票据探针

从仓库根目录运行，先按根 [开发规则](../../AGENTS.md) 使用 PM 准备环境，再安装锁定的前端依赖。`HERMES_PYTHON` 应指向完整项目环境的解释器，不要解析符号链接到缺少依赖的基础 Python。

```sh
npm ci
python evals/desktop_gateway_ticket_native/run.py --python "$HERMES_PYTHON" --output /private/tmp/native-ticket-results
python evals/desktop_gateway_ticket_native/run_multiplex.py --python "$HERMES_PYTHON" --output /private/tmp/native-multiplex-results
```

需要真实 macOS Electron 二进制；如自动发现失败，用 `--electron /absolute/path/to/Electron.app/Contents/MacOS/Electron`。不要跳过 npm 安装脚本或 Electron 下载。准备环境可能访问软件源。

运行时使用临时 HOME/HERMES_HOME、普通 Gateway 子进程和本地模拟推理，不调用付费模型；不安装后台服务。清理只针对本次拥有的进程。`build.mjs` 编译真实 `local-gateway.ts` 与 Python 票据桥，运行于 Electron main，不以 Node 或伪造平台代替。

- `run.py`：HTTP/WS 一次性票据、重放拒绝、错误实例/Profile 拒绝，以及负例后的正常请求。
- `run_multiplex.py`：一个 Gateway 服务多个 Profile，验证连接发现、冷 Profile 会话变更及跨 Profile 拒绝。
- 输出：指定目录中的 `receipt.json` 和进程日志；票据不应写入回执。

这里只证明已执行的原生 main 连接面，不覆盖完整 renderer、preload 或应用启动 UI。旧 Windows/Linux 分支不是当前交付范围，也不能用别的平台运行替代 macOS 证据。

旧的临时跨平台 workflow 模板已移除。不要把临时评测 workflow 当成正式 CI；如要纳入持续验收，先按仓库的 PM 环境与发布规则接入。本轮未运行此原生探针，当前 SHA 的完整验收状态未知。
