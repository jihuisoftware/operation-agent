---
sidebar_position: 2.5
title: "平台支持"
description: "通用运营版的 macOS、简体中文与共享运行时边界。"
---

# 平台支持

当前分支为通用运营平台，主题由用户输入或选择，公众号、小红书和抖音为首批渠道。主要入口为 **macOS Desktop**，界面仅支持**简体中文**。

## 当前产品范围

| 项目 | 支持范围 |
| --- | --- |
| 桌面系统 | macOS；启动、构建和打包入口执行平台检查 |
| 构建架构 | macOS arm64 / x64；具体架构的可下载产物以实际构建为准 |
| 界面语言 | 简体中文；旧语言设置与系统语言均归一到中文 |
| 本地后端 | Desktop 连接共享 Gateway，复用 Agent、调度和存储 |
| 辅助入口 | CLI / TUI 用于开发、自动化和诊断 |
| Windows / Linux 桌面 | 不属于当前产品范围，不提供对应打包命令 |
| 浏览器 Dashboard、Bot Mode、Kanban / Radio 界面 | 已移除 |

## 构建目标与支持边界 {#build-targets-and-support-priority}

普通桌面打包使用 `npm run dist:mac --workspace apps/desktop`，完整运行时包使用仓库根目录的 `scripts/build-bundle.sh`，后者要求干净工作区并打包 `HEAD`。

macOS DMG 用于安装，ZIP 用于更新。源码构建需要 Git 与 Xcode Command Line Tools。构建入口允许 macOS 不等于所有架构都已完成签名、安装及更新验收；发布必须依据实际产物验证。

当前不承诺已发布运营版安装器。上游 Hermes 下载站、旧版 bootstrap 安装器和其他分支的发布矩阵不代表本分支的交付状态。

## 不开放的能力 {#unsupported}

当前预设关闭多 Agent 协作工具、Kanban 工具与自动派单、MCP 服务、公共 API／Webhook、自动技能整理和插件自动更新检查。普通配置中的旧开关不能覆盖发行版范围。

`gateway/`、`tui_gateway/`、`hermes_cli/web_server*` 和部分跨平台实现继续为共享运行时保留。技术参考中的 Windows、Linux、Termux、消息适配器、delegation、Kanban 或 MCP 描述，不代表当前产品对这些入口作出支持承诺。

开始使用请参阅[安装说明](./installation.md)和[快速开始](./quickstart.md)。
