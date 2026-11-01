import {
  CRON_BLUEPRINTS_AREA,
  type CronBlueprintContribution,
  type HermesPlugin,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  SIDEBAR_NAV_PREFS_AREA,
  type SidebarNavContribution,
  type SidebarNavPrefsContribution,
  TITLEBAR_AREAS
} from '@hermes/plugin-sdk'
import { createRoot } from 'react-dom/client'

import { AccountsPage } from './accounts'
import { AnalysisPage } from './analysis-page'
import { BlueprintLibrary } from './blueprint-library'
import { LiveViewButton } from './live-view-button'
import { $loginActivity } from './login-activity'
import { OverviewPage } from './overview'
import { UpcomingOperations } from './upcoming'
import { Workbench } from './workbench'
import { WorkbenchPage } from './workbench-page'
import { OperationsWorker } from './worker'

declare const __OPERATIONS_DEBUG__: boolean

export default {
  id: 'operations',
  name: '每日自动运营',
  description: '目标、信息来源、规则执行与每日总结',
  register(ctx) {
    ctx.register({
      id: 'overview', area: ROUTES_AREA, title: '运营总览', data: { path: '/overview' },
      render: () => <OverviewPage ctx={ctx} />
    })
    ctx.register({
      id: 'overview-nav', area: SIDEBAR_NAV_AREA,
      data: { path: '/overview', label: '运营总览', codicon: 'dashboard' } satisfies SidebarNavContribution
    })

    for (const [stage, label, icon] of [['analytics', '数据分析', 'graph'], ['industry', '行业分析', 'globe']] as const) {
      ctx.register({ id: stage, area: ROUTES_AREA, title: label, data: { path: `/${stage}` }, render: () => <AnalysisPage ctx={ctx} stage={stage} /> })
      ctx.register({ id: `${stage}-nav`, area: SIDEBAR_NAV_AREA, data: { path: `/${stage}`, label, codicon: icon } satisfies SidebarNavContribution })
    }

    ctx.register({
      id: 'workbench-nav', area: SIDEBAR_NAV_AREA,
      data: { path: '/operations', label: '运营管理', codicon: 'notebook' } satisfies SidebarNavContribution
    })
    ctx.register({
      id: 'navigation-order', area: SIDEBAR_NAV_PREFS_AREA,
      data: { order: ['operations:overview-nav', 'cron', 'upcoming', 'activity', 'operations:workbench-nav', 'operations:analytics-nav', 'operations:industry-nav',
        'operations:accounts-nav', 'new-session', 'artifacts', 'capabilities', 'operations:debug-nav'] } satisfies SidebarNavPrefsContribution
    })

    if (__OPERATIONS_DEBUG__) {
      let disposed = false
      ctx.onDispose(() => { disposed = true })
      void import('./debug/entry').then(({ registerDebug }) => {
        if (!disposed) { registerDebug(ctx) }
      })
    }

    ctx.register({
      id: 'accounts',
      area: ROUTES_AREA,
      title: '账号登录',
      data: { path: '/accounts' },
      render: () => <AccountsPage ctx={ctx} />
    })
    ctx.register({
      id: 'accounts-nav',
      area: SIDEBAR_NAV_AREA,
      data: { path: '/accounts', label: '账号登录', codicon: 'account', activity: $loginActivity } satisfies SidebarNavContribution
    })
    ctx.register({
      id: 'blueprints',
      area: CRON_BLUEPRINTS_AREA,
      title: '运营蓝图',
      data: {
        render: ({ owner, view }) => <BlueprintLibrary ctx={ctx} owner={owner} view={view} />,
        renderUpcoming: ({ owner }) => <UpcomingOperations ctx={ctx} key={JSON.stringify(owner)} owner={owner} />
      } satisfies CronBlueprintContribution
    })
    ctx.register({
      id: 'live-view',
      area: TITLEBAR_AREAS.right,
      render: () => <LiveViewButton />
    })
    ctx.register({
      id: 'workbench',
      area: ROUTES_AREA,
      title: '运营管理',
      data: { path: '/operations' },
      render: () => <WorkbenchPage ctx={ctx} />
    })
    ctx.registerSettingsPage({ id: 'settings', title: '自动运营', render: () => <Workbench ctx={ctx} /> })
    const container = document.createElement('div')
    document.body.append(container)
    const root = createRoot(container)
    root.render(<OperationsWorker ctx={ctx} />)
    ctx.onDispose(() => {
      root.unmount()
      container.remove()
    })
  }
} satisfies HermesPlugin
