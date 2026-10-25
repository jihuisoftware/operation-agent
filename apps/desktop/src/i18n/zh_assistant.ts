import type { TranslationOverrides } from './define-locale'

export const zhAssistant = {
  assistant: {
    approval: {
      commandDetails: '命令详情',
      openSafetySettings: '打开安全设置',
      reconnect: '重新连接',
      timedOutSystemLine: '审批已超时，命令未执行。请让 Hermes 重试，或在“设置 → 安全 → 审批超时”中延长等待时间。'
    },
    catalogInstall: {
      alreadyInstalled: '已安装，保持现有配置',
      envVar: name => `${name} 环境变量`,
      missingEnv: names => `请设置 ${names} 以完成配置`,
      notEnabled: '已安装但未启用',
      phase: { downloading: '正在下载…', loading_tools: '正在加载工具…', python_packages: '正在安装 Python 依赖…' },
      requiresHermes: range => `需要 Hermes ${range}`,
      serverNotConnected: (server, reason) => `MCP 服务 ${server} 未连接${reason ? `：${reason}` : ''}`
    },
    thread: {
      errorAuthKinds: {
        api_key: {
          body: provider => `${provider} 的已保存密钥无效或已被撤销，请更新后重试。`,
          title: provider => `${provider} 拒绝了你的 API 密钥`
        },
        oauth: { title: provider => `${provider} 登录已过期` }
      },
      errorChooseModel: '选择模型',
      errorCodes: {
        SESSION_NOT_OWNED: {
          title: '此会话已在其他位置打开',
          body: '此会话正在另一个 Hermes 窗口或终端中打开。请先在那里关闭，再重新发送消息；也可以在此新建会话。'
        },
        SESSION_OWNER_BUSY: {
          title: 'Hermes 正在处理此会话',
          body: '另一轮任务正在运行，你的消息未能加入队列，也未被发送。请等该轮任务结束后重试。'
        },
        SESSION_OWNER_UNCONFIRMED: {
          title: '你的消息可能已经排队',
          body: '服务未及时确认收到消息。如果消息已进入队列，会在上一轮任务结束或问题解决后执行。请先检查会话，再决定是否重发。'
        },
        auth: {
          title: provider => `${provider} 拒绝了你的登录凭据`,
          body: provider => `${provider} 未接受已保存的凭据。请在设置中修正，或切换服务商后重新发送消息。`
        },
        auth_permanent: {
          title: provider => `${provider} 拒绝了你的登录凭据`,
          body: provider => `${provider} 的已保存凭据无效或已被撤销。请更新凭据，或切换服务商后重新发送消息。`
        },
        billing: {
          title: '余额不足',
          body: provider => `${provider} 账户余额已用完，请充值或切换服务商后重新发送。`
        },
        context_overflow: {
          title: '会话内容过长',
          body: '当前会话已超出模型的上下文容量。请压缩会话或新建会话后重新发送。'
        },
        disk_full: { title: '磁盘已满', body: '磁盘空间不足，Hermes 无法保存此会话。请释放空间后重试。' },
        free_tier_at_capacity: {
          title: '免登录聊天当前较繁忙',
          body: '免费登录后可跳过排队，也可以稍后重试。'
        },
        free_tier_disabled: {
          title: '免登录使用 Hermes 的功能暂时关闭',
          body: '使用 Nous 账户免费登录后即可继续聊天。'
        },
        free_tier_model_not_free: {
          title: '此模型需要登录后使用',
          body: 'Hermes 暂时使用免费模型。使用 Nous 账户免费登录后可选择更多模型。'
        },
        free_tier_outage: { title: '免费模型暂时无法正常回复', body: '请稍等片刻后重新发送消息。' },
        free_tier_rate_limited: {
          title: '免登录聊天额度已用完',
          body: '额度即将刷新。使用 Nous 账户免费登录后可获得更多额度。'
        },
        free_tier_refused: { title: 'Hermes 需要登录后才能发送此消息', body: '使用 Nous 账户登录是免费的。' },
        free_tier_route: {
          title: '当前连接无法访问免费模型',
          body: '请使用 Nous 账户免费登录，或检查 NOUS_INFERENCE_BASE_URL 设置。'
        },
        loop_error: {
          title: 'Hermes 陷入了重复执行',
          body: '回复中反复执行相同步骤，Hermes 已停止该任务。请重试；若再次发生，请新建会话。'
        },
        model_not_found: {
          title: '此模型不可用',
          body: provider => `${provider} 未向你的账户提供此模型。请选择其他模型后重新发送消息。`
        },
        no_reply: { title: '回复未完成', body: 'Hermes 结束了本轮任务，但没有给出回复。请重试以重新发送。' },
        payload_too_large: {
          title: '此消息过大',
          body: '请求超出了模型允许的大小。请压缩会话或新建会话后重新发送。'
        },
        stream_drop: { title: '回复连接中断', body: '回复尚未完成，连接就已断开。请重试以重新发送。' },
        truncated: { title: '回复被截断', body: '模型在完成回复前停止了输出。请重试以获取完整回复。' },
        upstream_blocked: {
          title: '请求被防火墙拦截',
          body: provider =>
            `${provider} 前端的防火墙或 CDN 在请求到达模型前将其拦截，密钥可能没有问题。请在设置中通过服务商的 extra_headers 添加 User-Agent 请求头，或切换服务商后重新发送。`
        }
      },
      errorCompressConversation: '压缩会话',
      errorCompressFailed: '无法压缩会话',
      errorDetails: '详情',
      errorLayerBodies: {
        auth: 'AI 服务拒绝了你的登录凭据。请检查此服务商的凭据后重新发送消息。',
        billing: '此服务商的账户余额已用完。请充值或切换服务商后重新发送。',
        disk: '磁盘空间不足，Hermes 无法保存此会话。请释放空间后重试。',
        gateway: 'Hermes 在开始回复时遇到内部错误。请重新发送消息；若持续出现，请发送诊断信息。',
        runtime: 'Hermes 在开始回复时遇到内部错误。请重新发送消息；若持续出现，请发送诊断信息。'
      },
      errorOpenHermesFolder: '打开 Hermes 文件夹',
      errorOpenHermesFolderFailed: '无法打开 Hermes 文件夹',
      errorSignInFreeTier: '使用 Nous 账户登录',
      errorToastTitle: 'Hermes 未能完成回复',
      errorUpdateApiKey: '更新 API 密钥',
      responseStopped: '回复已停止'
    }
  }
} satisfies TranslationOverrides
