import type { TranslationOverrides } from './define-locale'

export const zhChrome = {
  appTour: {
    capabilities: { title: '能力', text: '查看 Hermes 可使用的技能、工具和插件，也可以在这里添加。' },
    composer: { title: '在这里提问', text: '告诉助手你希望完成什么，输入 @ 可引用文件。' },
    messaging: { title: '消息平台', text: '通过 Telegram、Slack、Discord 等平台与 Hermes 对话。' },
    model: { title: '选择模型', text: '选择负责回答你的模型。' },
    modelLocal: '此电脑支持本地模型，可在“设置 → 服务商 → 本地模型”中配置。',
    newSession: { title: '新建会话', text: '每个新会话都有独立的上下文，建议每项任务使用一个会话。' },
    rightPane: { title: '工作面板', text: '在右侧打开文件、终端、审查面板和内置浏览器。' },
    sessions: { title: '你的会话', text: '所有会话都在这里，可以搜索、置顶或重新打开。' }
  },
  composer: { hiddenQueued: '配置说明' },
  connectorOffer: {
    body: '免费登录 Nous 账户，即可将已连接的 Gmail、Slack 等应用保存在账户中。',
    heading: '保留已连接的应用'
  },
  connectors: { checking: '正在检查应用…' },
  cron: {
    editJob: '编辑任务',
    lastRunFailed: '上次运行失败：',
    overdueSince: '已超期，原定时间：',
    runAgain: '重新运行'
  },
  desktop: { handoff: { startMessaging: '开始使用消息平台' } },
  errors: { boundaryDetails: '详情', sendDiagnostics: '发送诊断信息' },
  externalOpenFailed: {
    missing: { title: '找不到文件', message: '此文件不存在，可能已被删除、移动，或位于另一台电脑上。' }
  },
  fileMenu: { revealUnavailable: '此路径位于后端所在电脑上，本机无法打开。请使用“在文件树中显示”。' },
  freeTier: {
    busyBody: wait => `Nous 服务繁忙，Hermes 未能完成登录。请在 ${wait} 后重试，会话将为你保留。`,
    busyHeading: '即将完成',
    setupFailed: {
      gateClosed: '此版本需要 Nous 账户才能启动。请登录或免费注册，只需片刻。',
      generic: 'Hermes 未能配置免登录访问。你可以免费登录，或连接其他服务商。',
      locked: '此会话需要登录才能继续。请登录或免费注册 Nous 账户。',
      paused: '免登录功能暂时暂停，Hermes 会持续检查。免费登录后即可立即开始。',
      powRequired: 'Nous 服务要求进行工作量证明，但当前 Agent 尚不支持。请登录或免费注册 Nous 账户后继续。',
      rateLimited: wait => `当前使用人数较多，Hermes 将在 ${wait} 后重试。免费登录即可跳过等待。`,
      retrying: '正在重试…',
      serverError: 'Nous 服务暂时异常。请稍后点击“重试”，或暂时连接其他服务商。',
      signInBelow: '登录是免费的，请在下方选择 Nous。',
      tryAgain: '重试',
      unreachable: '无法连接 Nous 服务。请检查网络后点击“重试”，或暂时连接其他服务商。'
    },
    unreachableBody: 'Hermes 无法连接 Nous 服务以完成登录。请检查网络后重试，会话将为你保留。'
  },
  gatewayGroupOpen: {
    lookupFailed: '无法查询此服务中的分组，请重试。',
    missing: '此服务分组已不存在。',
    opening: '正在打开服务分组…'
  },
  install: { openLogs: '打开日志', probeErrorDetails: '详情' },
  keybinds: {
    clear: '清除',
    actions: {
      'hud.snapToPointer': '将悬浮窗口移到指针位置（窗口打开时全局可用）',
      'view.closeTerminal': '关闭终端',
      'view.cycleSidebarGrouping': '切换侧边栏分组方式',
      'view.newTerminal': '新建终端',
      'view.nextTerminal': '下一个终端',
      'view.prevTerminal': '上一个终端',
      'view.tabSlot.1': '切换到第 1 个标签页',
      'view.tabSlot.2': '切换到第 2 个标签页',
      'view.tabSlot.3': '切换到第 3 个标签页',
      'view.tabSlot.4': '切换到第 4 个标签页',
      'view.tabSlot.5': '切换到第 5 个标签页',
      'view.tabSlot.6': '切换到第 6 个标签页',
      'view.tabSlot.7': '切换到第 7 个标签页',
      'view.tabSlot.8': '切换到第 8 个标签页',
      'view.tabSlot.9': '切换到第 9 个标签页',
      'view.toggleHud': '切换悬浮窗口'
    }
  },
  messaging: {
    openLogs: '打开日志',
    restartAgain: '再次重启',
    restartFailedManualDetail: '请再次重启；若仍失败，请打开日志并发送诊断信息。'
  },
  notifications: {
    actions: {
      openGateways: '打开连接管理',
      openKeys: '打开密钥管理',
      openMaintenance: '打开维护页面',
      restartHermes: '重启 Hermes'
    },
    compressDeferredDone: '上下文压缩已完成',
    errors: {
      restartHermesFailed: '无法重启 Hermes',
      rpcOutOfSync: '应用与后端版本不一致，请更新两者。',
      storageFailure: 'Hermes 无法写入数据文件夹，请打开维护页面检查并修复。'
    }
  },
  onboarding: {
    errorDetails: '详情',
    signInDidNotFinish: provider => `${provider} 登录未完成。请检查网络后重试，或选择其他服务商。`,
    tryAgain: '重试',
    useApiKeyInstead: '使用 API 密钥'
  },
  preview: { missingTarget: '此电脑上不存在该路径' },
  profiles: {
    status: {
      needsInput: count => `${count} 个会话等待你回答`,
      unread: count => `${count} 个未读会话`,
      working: count => `${count} 个会话正在运行`
    }
  },
  prompts: { reconnect: '重新连接' },
  settings: {
    fieldDescriptions: {
      'stt.streaming': '边说边显示转写文本（支持 OpenAI、xAI、ElevenLabs）；发生错误时回退为录音转写。'
    },
    fieldLabels: {
      'stt.deepinfra.model': 'DeepInfra 语音识别模型',
      'stt.openai.streamingModel': 'OpenAI 流式语音识别模型',
      'stt.streaming': '流式语音识别',
      'stt.xai.model': 'xAI 语音识别模型'
    },
    localModels: {
      downloadEtaHours: (hours, minutes) => (minutes ? `${hours} 小时 ${minutes} 分钟` : `${hours} 小时`),
      downloadEtaMinutes: count => `${count} 分钟`,
      downloadEtaSeconds: count => `${count} 秒`,
      downloadPauseFailed: model => `无法暂停 ${model} 的下载`,
      downloadResumeFailed: model => `无法继续下载 ${model}`
    },
    model: { mainAppliedMessage: model => `新会话将使用 ${model}。`, mainAppliedTitle: '主模型已更新' },
    plugins: { disable: '停用', enable: '启用' },
    toolsets: {
      nousAuthFailedMessage: '请重试。',
      nousAuthTryAgain: '重试',
      postSetupOpenLogs: '打开日志',
      postSetupRunAgain: '重新运行',
      terminalBackend: {
        openBackendSettings: '打开终端设置',
        switchedToLocal: '终端命令已切换为本地执行，将在新会话中生效。',
        unavailableMessage: backend =>
          `${backend} 尚未就绪，Hermes 暂时无法执行终端命令。请切换为本地执行，或完成 ${backend} 的配置后重试。`,
        unavailableTitle: '终端命令暂不可用',
        useLocal: '使用本地终端'
      }
    },
    uninstallSection: {
      dataKept: path => `配置、会话和密钥保存在 ${path}，卸载应用不会删除它们。`,
      managedBody: '此安装由系统管理，Hermes 无法自行卸载。',
      openAppsSettings: '打开系统应用设置'
    }
  },
  shell: {
    statusbar: {
      planUsageTitle: (used, resetsIn) => `套餐用量已使用 ${used}${resetsIn ? ` · ${resetsIn} 后重置` : ''} · 打开账单`,
      togglePlanUsage: '套餐用量'
    }
  },
  sidebar: {
    storageCorrupt: {
      action: '请先退出使用此配置的 Hermes，再以只读方式检查文件或恢复快照：',
      body: profiles =>
        `Hermes 无法读取 ${profiles} 的完整会话历史。列表中缺失的会话并未删除，而是存储它们的文件已损坏。`,
      guide: '恢复指南',
      title: '会话数据库已损坏'
    }
  },
  updates: {
    applyStatus: { owed: steps => `后端已更新，但仍需完成：${steps}。请重新运行 hermes update。` },
    connectionSettings: '连接设置',
    openDownloadPage: '打开下载页面'
  }
} satisfies TranslationOverrides
