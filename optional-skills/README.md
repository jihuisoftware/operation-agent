# 运营场景可选技能

此目录保存技能正文及配套脚本、参考资料和模板，不会默认复制到用户技能目录或加入系统提示。
安装来源由 `tools/skills_hub_official.py` 的 `OptionalSkillSource` 扫描。当前保留 57 项，
以内容制作、公开资料采集、运营分析、营销页面、电商与办公协作为范围。

## 保留范围

| 分类 | 技能 |
| --- | --- |
| communication | one-three-one-rule |
| creative | ai-presenter-video, anatomy, archify, ascii-art, audiocraft-audio-generation, auteur, baoyu-article-illustrator, baoyu-comic, brag, brag-slim, comfyui, concept-diagrams, creative-ideation, draw-your-font, dream-loop, excalidraw, heartmula, hyperframes, impeccable, ip-as-logo, meme-generation, mono-color, pixel-art, pretext, simple-english, sketch, social-media-content-calendar, system-atlas, tldraw-offline |
| data-science | jupyter-notebook |
| devops | inference-sh-cli, watchers |
| email | agentmail |
| finance | excel-author, pptx-author |
| mcp | mcporter |
| mlops | stable-diffusion, whisper |
| productivity | decision-questionnaire, here-now, live-dashboard, shopify, siyuan |
| research | blogwatcher, duckduckgo-search, osint-investigation, parallel-cli, qmd, rss-feeds, scrapling, searxng-search |
| security | 1password |
| social-media | reddit-reading |
| web-development | cloudflare-temporary-deploy, publish-site, scrollcraft |

保留表格与演示作者技能，移除证券估值和并购建模；保留 Whisper 转写与 Stable Diffusion
素材生成，移除训练、微调和推理服务基础设施。`inference-sh-cli` 位于 devops 分类，
但用途是生成图像和视频，因此保留。分类名称不等同于能力边界。

`mcporter` 是按需使用的独立命令行客户端，不会打开运营版已关闭的内置 MCP 服务；
`tldraw-offline` 等外部集成仍须满足各自前置条件。保留不表示默认启用、已安装依赖，
或已通过当前 macOS 环境与真实账号验收。

## 本版移除

本轮从 152 项裁剪到 57 项，移除 95 项及其专属资源。理由包括：

- 模型训练、向量服务、代码开发与容器运维不属于当前运营产品交付范围。
- 区块链、支付交易、证券估值、游戏、健康设备、智能家居等属于未接入的专用场景。
- Kanban、多 Agent 委派和元宝群功能已退出当前产品界面及工具服务范围。
- 学术研发、攻防测试、数据经纪商信息删除等不属于常规内容与增长运营。

| 原分类 | 已移除技能 |
| --- | --- |
| autonomous-ai-agents | agent-merge-conflict-arbiter, antigravity-cli, blackbox, dynamic-workflow, grok, honcho, openhands |
| blockchain | evm, hyperliquid, solana |
| creative | kanban-video-orchestrator, unreal-mcp |
| devops | actual-setup, docker-management, hermes-s6-container-supervision, pinggy-tunnel, setup-wizard-generator |
| dogfood | adversarial-ux-test |
| finance | 3-statement-model, comps-analysis, dcf-model, lbo-model, merger-model, polymarket, stocks |
| gaming | minecraft-modpack-server, pokemon-player |
| health | fitness-nutrition, neuroskill-bci |
| mcp | fastmcp, mcp-oauth-remote-gateway |
| mlops | accelerate, chroma, clip, evaluating-llms-harness, weights-and-biases, faiss, flash-attention, guidance, huggingface-tokenizers, llama-cpp, outlines, serving-llms-vllm, instructor, lambda-labs, llava, modal, huggingface-hub, segment-anything-model, nemo-curator, obliteratus, peft, pinecone, pytorch-fsdp, pytorch-lightning, qdrant, dspy, saelens, simpo, slime, tensorrt-llm, torchtitan, axolotl, trl-fine-tuning, unsloth |
| payments | mpp-agent, stripe-link-cli, stripe-projects |
| productivity | canvas, memento-flashcards, property-listings, shop, telephony |
| research | bioinformatics, darwinian-evolver, domain-intel, drug-discovery, gitnexus-explorer, pinecone-research, research-paper-writing |
| security | godmode, oss-forensics, sherlock, unbroker, web-pentest |
| smart-home | openhue |
| software-development | ast-grep, code-wiki, grill-me, pr-lens, rest-graphql-debug, subagent-driven-development |
| web-development | har-derived-api-client, page-agent |
| yuanbao | yuanbao |

## 安装与边界

例如：

```bash
hermes skills install official/creative/social-media-content-calendar
hermes skills install official/research/rss-feeds
```

本轮只清理仓库分发内容，不删除用户已安装技能、配置或凭证，不改变会话提示缓存及安装机制。
技能中心仍支持查询上游远程目录；本地清理并不构成远程安装黑名单。
运营主题仍由用户选择，移除行业专用技能不限制通过现有检索、浏览器和文件能力处理相关主题。
网站技能页面、侧栏及中英文目录随此次清理同步更新，专属测试随被删除实现退役，通用安装测试保留。
