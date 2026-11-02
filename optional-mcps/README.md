# 运营场景可选 MCP 目录

此目录保存第三方 MCP 的安装清单（`<name>/manifest.yaml`），描述服务地址、
认证方式、配置提示和推荐触发词，不包含 MCP 服务实现，也不会因目录存在而自动安装。
共享目录加载器与分发构建按文件扫描，无需维护额外注册表。

当前运营版在 [产品范围](../hermes_cli/data/operations-profile.json) 中设置
`services.mcp=false`。以下条目仅作为与运营相关的可选集成保留，不表示当前产品
已开放这些服务，也不代表远端服务已完成真实账号验收。

## 保留范围

| 场景 | 清单 |
| --- | --- |
| 设计、内容与媒体素材 | canva、figma、gamma、cloudinary、comfy-cloud |
| 文档、文件与团队协作 | notion、craft、dropbox、miro、fireflies |
| 排期、任务与业务表格 | airtable、asana、clickup、monday、todoist、calendly |
| 客户关系与营销 | attio、close、intercom、klaviyo |
| 搜索与数据分析 | algolia、amplitude、mixpanel、motherduck |
| 内容站点与流程集成 | wordpress-com、webflow、n8n-official |

## 本版已移除

按当前内容、品牌、活动及增长运营场景裁剪，暂不随产品分发以下清单：

- 开发文档、代码与游戏开发：aws-knowledge、context7、deepwiki、hugging_face、
  microsoft-learn、twilio-docs、gitlab、linear、atlassian、postman、semgrep、unreal-engine。
- 部署、监控与网络运维：betterstack、buildkite、circleci、cloudflare、datadog、
  globalping、grafana、netlify、railway、sentry、vercel。
- 应用数据库基础设施：neon、prisma-postgres、supabase。保留 motherduck 用于数据分析，
  不将数据库开发和运维作为运营助手的默认集成方向。
- 支付、银行与证券交易：stripe、paypal、square、plaid、robinhood、twelve-data。
- 旅游、运动、招聘、线下雇佣与科学计算：alltrails、kiwi、trivago、strava、indeed、
  rentahuman、wolfram。

清理仅影响仓库分发的安装目录，不删除用户已有的 `mcp_servers` 配置、凭证或已安装文件，
不修改共享 MCP 协议、认证、安装及运行时实现。业务主题仍由用户选择，
移除某行业专用清单不限制用户通过现有检索、浏览器、文件和技能能力开展该行业运营。
后续新增集成应以明确业务需求为依据，继续遵循清单校验及依赖固定版本约束。
