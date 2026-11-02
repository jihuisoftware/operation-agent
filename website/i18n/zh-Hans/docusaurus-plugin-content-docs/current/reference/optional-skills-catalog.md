---
sidebar_position: 9
title: "可选技能目录"
description: "hermes-agent 附带的官方可选技能 — 通过 hermes skills install official/<category>/<skill> 安装"
---

# 可选技能目录

可选技能随 hermes-agent 一起发布，位于 `optional-skills/` 目录下，但**默认未激活**。请显式安装：

```bash
hermes skills install official/<category>/<skill>
```

示例：

```bash
hermes skills install official/creative/social-media-content-calendar
hermes skills install official/research/rss-feeds
```

下方每个技能均链接至专属页面，包含完整定义、配置和使用说明。

卸载方式：

```bash
hermes skills uninstall <skill-name>
```

## communication

| 技能 | 描述 |
|-------|-------------|
| [**one-three-one-rule**](/user-guide/skills/optional/communication/communication-one-three-one-rule) | 用于技术提案和权衡分析的结构化决策框架。当用户面临多种方案选择（架构决策、工具选型、重构策略、迁移路径）时，本技能提供系统化的分析流程。 |

## creative

| 技能 | 描述 |
|-------|-------------|
| [**ascii-art**](/user-guide/skills/optional/creative/creative-ascii-art) | ASCII 艺术：pyfiglet、cowsay、boxes、图像转 ASCII。 |
| [**audiocraft-audio-generation**](/user-guide/skills/optional/creative/creative-audiocraft-audio-generation) | AudioCraft：MusicGen 文本转音乐、AudioGen 文本转音效。 |
| [**comfyui**](/user-guide/skills/optional/creative/creative-comfyui) | 使用 ComfyUI 生成图像、视频和音频——安装、启动、管理节点/模型、运行带参数注入的工作流。使用官方 comfy-cli 管理生命周期，通过 REST/WebSocket API 直接执行。 |
| [**concept-diagrams**](/user-guide/skills/optional/creative/creative-concept-diagrams) | 生成扁平、极简、支持亮色/暗色模式的 SVG 图表，输出为独立 HTML 文件，采用统一的教育视觉语言，包含 9 种语义色阶、句首大写排版及自动暗色模式。最适合教育和说明类内容。 |
| [**excalidraw**](/user-guide/skills/optional/creative/creative-excalidraw) | 手绘风格的 Excalidraw JSON 图表（架构、流程、时序）。 |
| [**heartmula**](/user-guide/skills/optional/creative/creative-heartmula) | HeartMuLa：根据歌词 + 标签生成类 Suno 风格的歌曲。 |
| [**hyperframes**](/user-guide/skills/optional/creative/creative-hyperframes) | 使用 HyperFrames 创建基于 HTML 的视频合成、动态标题卡、社交叠层、字幕访谈视频、音频响应视觉效果及着色器转场。HTML 是视频的唯一来源。适用于用户希望制作任何视频内容的场景。 |
| [**meme-generation**](/user-guide/skills/optional/creative/creative-meme-generation) | 通过选取模板并使用 Pillow 叠加文字来生成真实的 meme 图片，输出实际的 .png 文件。 |
| [**pretext**](/user-guide/skills/optional/creative/creative-pretext) | 使用 @chenglou/pretext 构建创意浏览器 demo——无 DOM 的文本布局，支持 ASCII 艺术、绕障碍物的排版流、文字即几何游戏、动态排版和文字驱动的生成艺术。生成单文件 HTML。 |
| [**sketch**](/user-guide/skills/optional/creative/creative-sketch) | 一次性 HTML 原型：生成 2-3 个设计变体供对比。 |

## data-science

| 技能 | 描述 |
|-------|-------------|
| [**jupyter-notebook**](/user-guide/skills/optional/data-science/data-science-jupyter-notebook) | 通过实时 Jupyter kernel（hamelnb）进行迭代式 Python 开发。 |

## devops

| 技能 | 描述 |
|-------|-------------|
| [**inference-sh-cli**](/user-guide/skills/optional/devops/devops-inference-sh-cli) | 通过 inference.sh CLI（infsh）运行 150+ AI 应用 — 图像生成、视频创作、LLM、搜索、3D、社交自动化。使用终端工具。触发词：inference.sh、infsh、ai apps、flux、veo、图像生成、视频生成、seedrea 等。 |
| [**watchers**](/user-guide/skills/optional/devops/devops-watchers) | 轮询 RSS、JSON API 和 GitHub，并使用水印去重。 |

## email

| 技能 | 描述 |
|-------|-------------|
| [**agentmail**](/user-guide/skills/optional/email/email-agentmail) | 通过 AgentMail 为 agent 提供专属邮箱。使用 agent 专属邮件地址（如 hermes-agent@agentmail.to）自主发送、接收和管理邮件。 |

## finance

| 技能 | 描述 |
|-------|-------------|
| [**excel-author**](/user-guide/skills/optional/finance/finance-excel-author) | 使用 openpyxl 无头构建可审计的 Excel 工作簿 — 蓝/黑/绿单元格规范、公式优先于硬编码、命名区域、余额校验、敏感性分析表。适用于财务模型、审计输出、对账。 |
| [**pptx-author**](/user-guide/skills/optional/finance/finance-pptx-author) | 使用 python-pptx 无头构建 PowerPoint 演示文稿。与 excel-author 配合，制作每个数字均可追溯至工作簿单元格的模型支撑型幻灯片。适用于 pitch deck、投委会备忘录、盈利说明。 |

## mcp

| 技能 | 描述 |
|-------|-------------|
| [**mcporter**](/user-guide/skills/optional/mcp/mcp-mcporter) | 使用 mcporter CLI 列出、配置、鉴权并直接调用 MCP 服务器/工具（HTTP 或 stdio），包括临时服务器、配置编辑及 CLI/类型生成。 |

## mlops

| 技能 | 描述 |
|-------|-------------|
| [**stable-diffusion-image-generation**](/user-guide/skills/optional/mlops/mlops-stable-diffusion) | 通过 HuggingFace Diffusers 使用 Stable Diffusion 模型进行最先进的文本到图像生成。适用于从文本 prompt 生成图像、图像到图像转换、图像修复或构建自定义扩散流水线的场景。 |
| [**whisper**](/user-guide/skills/optional/mlops/mlops-whisper) | OpenAI 的通用语音识别模型。支持 99 种语言、转录、翻译为英语及语言识别。六种模型规格，从 tiny（39M 参数）到 large（1550M 参数）。适用于语音转文字、播客转录等场景。 |

## productivity

| 技能 | 描述 |
|-------|-------------|
| [**here.now**](/user-guide/skills/optional/productivity/productivity-here-now) | 将静态站点发布至 &#123;slug&#125;.here.now，并将私有文件存储在云端 Drive 中以供 agent 间交接。 |
| [**shopify**](/user-guide/skills/optional/productivity/productivity-shopify) | 通过 curl 使用 Shopify Admin 和 Storefront GraphQL API。支持商品、订单、客户、库存、元字段。 |
| [**siyuan**](/user-guide/skills/optional/productivity/productivity-siyuan) | 通过 curl 使用 SiYuan Note API，在自托管知识库中搜索、读取、创建和管理块与文档。 |

## research

| 技能 | 描述 |
|-------|-------------|
| [**blogwatcher**](/user-guide/skills/optional/research/research-blogwatcher) | 通过 blogwatcher-cli 工具监控博客和 RSS/Atom 订阅源。 |
| [**duckduckgo-search**](/user-guide/skills/optional/research/research-duckduckgo-search) | 通过 DuckDuckGo 免费网络搜索 — 文本、新闻、图片、视频。无需 API 密钥。优先使用已安装的 `ddgs` CLI；仅在确认当前运行时中 `ddgs` 可用后才使用 Python DDGS 库。 |
| [**osint-investigation**](/user-guide/skills/optional/research/research-osint-investigation) | 公开记录 OSINT 调查框架 — SEC EDGAR 文件、USAspending 合同、参议院游说记录、OFAC 制裁、ICIJ 离岸泄露、纽约市房产记录（ACRIS）、OpenCorporates 注册信息、CourtListener 法院记录、Wayback Machine 等。 |
| [**parallel-cli**](/user-guide/skills/optional/research/research-parallel-cli) | Parallel CLI 的可选厂商技能 — agent 原生网络搜索、提取、深度研究、数据增强、FindAll 及监控。优先使用 JSON 输出和非交互式流程。 |
| [**qmd**](/user-guide/skills/optional/research/research-qmd) | 使用 qmd（一款结合 BM25、向量搜索和 LLM 重排序的混合检索引擎）在本地搜索个人知识库、笔记、文档和会议记录。支持 CLI 和 MCP 集成。 |
| [**scrapling**](/user-guide/skills/optional/research/research-scrapling) | 使用 Scrapling 进行网页抓取 — 通过 CLI 和 Python 实现 HTTP 获取、隐身浏览器自动化、Cloudflare 绕过及爬虫抓取。 |
| [**searxng-search**](/user-guide/skills/optional/research/research-searxng-search) | 通过 SearXNG 免费元搜索 — 聚合 70+ 搜索引擎的结果。可自托管或使用公共实例。无需 API 密钥。当网络搜索工具集不可用时自动回退。 |

## security

| 技能 | 描述 |
|-------|-------------|
| [**1password**](/user-guide/skills/optional/security/security-1password) | 配置并使用 1Password CLI（op）。适用于安装 CLI、启用桌面应用集成、登录及为命令读取/注入密钥的场景。 |

## 贡献可选技能

向仓库添加新的可选技能：

1. 在 `optional-skills/<category>/<skill-name>/` 下创建目录
2. 添加包含标准 frontmatter 的 `SKILL.md`（name、description、version、author）
3. 在 `references/`、`templates/` 或 `scripts/` 子目录中包含所有支撑文件
4. 提交 pull request — 合并后该技能将出现在本目录并获得专属文档页面
