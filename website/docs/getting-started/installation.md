---
sidebar_position: 2
title: "安装与开发启动"
description: "在 macOS 上准备通用运营版 Desktop。"
---

# 安装与开发启动

本页适用于当前运营分支：**macOS Desktop、简体中文**。先确认使用的是本分支源码或本分支实际构建的安装包；上游 Hermes 的公开安装器不等同于运营版。详见[平台支持](./platform-support.md)。

## 从源码启动

需要 macOS、Git 和 Xcode Command Line Tools。在取得本分支源码后，从仓库根目录执行：

```bash
export HERMES_HOME="$HOME/hermes-operations-dev"
export HERMES_RUNTIME_DIR="$HERMES_HOME/tools"
source ./activate
npm ci
HERMES_DESKTOP_HERMES_ROOT="$PWD" npm run dev --workspace apps/desktop
```

`activate` 使用 PM 准备工具链，`npm ci` 安装 JavaScript 工作区依赖。Node/npm 版本以根目录 `package.json` 的 `engines` 为准。再次开发时使用相同的目录配置并重新激活，不使用 raw pip/uv 修改 Hermes 管理的环境。

需要临时隔离应用实例与用户数据时，在已准备好的开发环境执行：

```bash
scripts/dev-sandbox.sh -- npm run dev --workspace apps/desktop
```

退出后临时数据会清理；需保留时加 `--persistent`。更多依赖管理机制见[PM 参考](../reference/package-management.md#developer-workflow)，其中其他系统的兼容性说明不扩展本版支持范围。

## 使用本分支的 macOS 安装包

仅在已经取得本分支构建、核验的产物时使用此路径。打开对应架构的 DMG，将 `Hermes.app` 放入应用程序目录。Bundled 产物自带运行时，首次启动不重新构建基础 Python 环境；模型服务、可选能力及下载仍可能需要网络。

本地完整构建入口为 `scripts/build-bundle.sh`，要求干净工作区；普通 `npm run dist:mac --workspace apps/desktop` 不会准备全新的运行时。具体签名、公证与发布要求见仓库中的 `apps/desktop/BUILDING.md`。

## 首次启动

在 Desktop 中配置模型与凭证，先验证一条普通对话。图片生成、配音等能力按服务配置验证。产品范围覆盖旧配置，不能通过旧的语言、机器人、Kanban 或 MCP 开关恢复被关闭功能。

Desktop 自动通过 `hermes gateway ensure --json` 获取或启动本地 Gateway，不需要手动启动 `serve` 或 Dashboard。退出 Desktop 不会停止 Gateway；需要停止时，在对应环境执行 `hermes gateway stop`。

业务流程与验证方法见[快速开始](./quickstart.md)。
