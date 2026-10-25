import type { TranslationOverrides } from './define-locale'

export const zhCapabilities = {
  catalog: {
    developer: {
      docs: '开发文档',
      heading: '开发者模式',
      pitch: '开发了工具、连接器、插件或扩展？',
      pitchFollowUp: '想开发但不知如何开始？',
      submit: '提交扩展',
      title: '为 Hermes 开发'
    },
    discoverKind: kind => `发现${kind}`,
    moreToExplore: '更多内容',
    moreToExploreBlurb: '在这里探索目录中的其他内容。',
    nextSlide: '下一个精选',
    previousSlide: '上一个精选',
    skillsFor: category => `${category}相关技能。`,
    slideOf: (index, count) => `第 ${index} 项，共 ${count} 项`,
    tier: '来源级别',
    tierLabels: { community: '社区', official: '官方', verified: '已认证' },
    tiers: {
      official: { blurb: '由 Nous Research 开发和维护。', title: '官方插件' },
      verified: { blurb: '由集成服务所属公司提供，并经 Nous 认证。', title: '认证插件' }
    },
    toolsets: {
      callCount: count => `${count} 次调用`,
      essentials: '常用工具',
      essentialsBlurb: '大多数 Hermes 任务会使用的基础工具。',
      mostUsed: '使用最多',
      mostUsedBlurb: '当前配置中 Hermes 最常使用的工具集。',
      themes: {
        connect: { blurb: '连接账户、其他助手、智能家居及更多搜索服务。', label: '连接与协作' },
        create: { blurb: '理解图片与视频、转写语音并生成媒体内容。', label: '视听与创作' },
        more: { blurb: '当前配置可以启用的其他工具。', label: '更多工具' },
        recall: { blurb: 'Hermes 的记忆，以及可以检索的技能和历史记录。', label: '记忆与知识' },
        work: { blurb: '操作浏览器和桌面、编辑文件、运行代码及安排任务。', label: '浏览、工作与自动化' }
      },
      toolCount: count => `${count} 个工具`
    }
  },
  skills: {
    hub: {
      installBlockedMessage: (findings, unverified) =>
        `安全扫描发现${findings > 0 ? ` ${findings} 项待检查问题` : '风险模式'}${unverified ? '，且此技能来源未经验证' : ''}。请先阅读扫描结果，再决定是否信任作者。`,
      installBlockedTitle: name => `无法安装 ${name}`,
      openLog: '打开日志',
      viewScan: '查看扫描结果'
    },
    plugins: {
      serverStates: {
        app_not_running: '应用未运行',
        connected: '已连接',
        endpoint_unavailable: '服务端点不可用',
        hermes_not_connected: '未建立 MCP 连接',
        missing_app: '应用未安装',
        no_interactive_session: '没有交互会话',
        unknown: '状态未知',
        unsupported_gpu: '不支持此 GPU',
        version_too_old: '版本过旧'
      },
      settingsForm: {
        optional: '（选填）',
        required: '必填',
        save: '保存设置',
        saveFailed: name => `无法保存 ${name} 的设置`,
        saved: name => `${name} 的设置已保存。`,
        secretSet: '••••••••（已设置）',
        secretStoredAs: env => `以 ${env} 保存到当前配置的 .env 中，不写入 config.yaml。留空可保留现有值。`
      },
      settingsToggle: name => `设置：${name}`,
      toolsetOff: (name, profile) => `已为 ${profile} 停用 ${name} 工具`,
      toolsetOn: (name, profile) => `已为 ${profile} 启用 ${name} 工具`,
      toolsetToggleFailed: name => `无法切换 ${name} 工具的启用状态，桌面面板保持不变`,
      updateConsentBody: (name, sha) =>
        `${name} 的目录新版本（${sha}）增加了当前版本没有的能力。请仅在信任以下新增能力时更新：`,
      updateConsentConfirm: '应用更新',
      updateConsentTitle: name => `${name} 申请新增能力`,
      updateScanBlocked: name => `安全扫描将 ${name} 的更新判定为危险并已阻止，无法跳过。`,
      updateScanBody: (name, count) =>
        `${name} 的更新被标记为需要谨慎处理（${count} 项发现）。每次更新都会扫描，请仅在信任来源时应用：`,
      updateScanConfirm: '仍然更新',
      updateScanMore: count => `另有 ${count} 项`,
      updateScanTitle: name => `安全扫描发现 ${name} 存在风险`,
      updatedGit: name => `${name} 已更新到最新提交。`
    }
  }
} satisfies TranslationOverrides
