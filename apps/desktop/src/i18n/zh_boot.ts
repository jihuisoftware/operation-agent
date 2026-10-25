import type { TranslationOverrides } from './define-locale'

export const zhBoot = {
  boot: {
    causes: {
      diskFull: '磁盘已满，Hermes 无法启动。',
      exitedEarly: 'Hermes 后台服务在启动后立即停止。',
      installMissing: 'Hermes 的部分安装文件缺失，请选择“修复安装”以恢复。',
      permission: 'Hermes 无权写入其数据文件夹。',
      portInUse: '其他程序正在占用 Hermes 所需的网络端口。',
      timedOut: 'Hermes 后台服务未及时响应。'
    },
    errors: {
      connectionSettings: '连接设置',
      gatewaySignInRequiredDetail: '请重新登录以恢复连接。你的会话和设置已保留。',
      openLogs: '打开日志',
      reconnectNow: '立即重连',
      restartHermes: '重启 Hermes',
      signInAgain: '重新登录'
    },
    failure: { details: '详情' },
    updateHold: {
      checkAgain: '重新检查',
      confirmBody:
        '残留的更新进程可能仍在修改 Hermes 文件。现在启动可能加载尚未更新完整的安装，导致应用无法工作，直到再次执行更新。Hermes 会在日志中记录本次选择，并保留更新标记。',
      confirmKeepWaiting: '继续等待',
      confirmStart: '仍然启动',
      confirmTitle: '更新尚未释放文件，仍要启动 Hermes 吗？',
      description: 'Hermes 正在等待更新释放文件，以免加载仍在修改中的内容。等待结束后将自动启动。',
      heldByProcess: pid => `更新进程 ${pid} 已退出，但它启动的其他进程仍在占用 Hermes 安装文件。`,
      heldUnknown: '更新已退出，但它启动的其他进程仍在占用 Hermes 安装文件。',
      lastChecked: time => `上次检查：${time}`,
      openLogs: '打开日志',
      quit: '退出 Hermes',
      recoveryHint:
        '通常会在几分钟内恢复。若持续等待，请退出 Hermes，结束残留的 git 或 hermes 进程（或重启电脑），然后重新打开。',
      since: time => `自 ${time} 起等待`,
      startAnyway: '仍然启动…',
      startAnywayRefused: '在启动前，占用安装文件的进程发生了变化。请检查后重试。',
      title: '先前的更新仍在占用 Hermes',
      titleUnverified: '无法确认上次更新是否完成',
      unverified: '更新助手暂时无法检查安装文件由谁占用，Hermes 会继续检查。'
    }
  }
} satisfies TranslationOverrides
