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
import { Button, host } from '@hermes/plugin-sdk'
import { createRoot } from 'react-dom/client'

import { AccountsPage } from './accounts'
import { LegacyPage } from './legacy-page'
import { LiveViewButton } from './live-view-button'
import { $loginActivity } from './login-activity'
import { OverviewPage } from './overview'
import { PlanEditor } from './plan-editor'
import { type Section, SectionPage, sections } from './section-page'
import { UpcomingOperations } from './upcoming'
import { OperationsWorker } from './worker'

declare const __OPERATIONS_DEBUG__: boolean

export default {
  id: 'operations',
  name: '每日自动运营',
  description: '目标、信息来源、规则执行与每日总结',
  register(ctx) {
    ctx.register({
      id: 'overview',
      area: ROUTES_AREA,
      title: '运营总览',
      data: { path: '/overview' },
      render: () => <OverviewPage ctx={ctx} />
    })
    ctx.register({
      id: 'overview-nav',
      area: SIDEBAR_NAV_AREA,
      data: { path: '/overview', label: '首页', codicon: 'dashboard' } satisfies SidebarNavContribution
    })

    for (const section of Object.keys(sections) as Section[]) {
      const { title, icon } = sections[section]
      ctx.register({
        id: section,
        area: ROUTES_AREA,
        title,
        data: { path: `/${section}` },
        render: () => <SectionPage ctx={ctx} section={section} />
      })
      ctx.register({
        id: `${section}-nav`,
        area: SIDEBAR_NAV_AREA,
        data: { path: `/${section}`, label: title, codicon: icon } satisfies SidebarNavContribution
      })
    }

    for (const stage of ['analytics', 'industry']) {
      ctx.register({
        id: stage,
        area: ROUTES_AREA,
        data: { path: `/${stage}` },
        render: () => <LegacyPage to={`/analysis?tab=${stage}`} />
      })
    }

    ctx.register({
      id: 'navigation-order',
      area: SIDEBAR_NAV_PREFS_AREA,
      data: {
        home: '/overview',
        hide: ['upcoming', 'activity', 'artifacts'],
        order: [
          'operations:overview-nav',
          'cron',
          'operations:materials-nav',
          'operations:analysis-nav',
          'operations:content-nav',
          'operations:interactions-nav'
        ],
        footer: [
          'operations:accounts-nav',
          'new-session',
          'operations:settings-nav',
          'capabilities',
          'operations:debug-nav'
        ],
        labels: { cron: '任务', 'new-session': 'AI 助手', capabilities: '扩展工具' }
      } satisfies SidebarNavPrefsContribution
    })
    ctx.register({
      id: 'settings-nav',
      area: SIDEBAR_NAV_AREA,
      data: { path: '/settings', label: '设置', codicon: 'settings-gear' } satisfies SidebarNavContribution
    })

    if (__OPERATIONS_DEBUG__) {
      let disposed = false
      ctx.onDispose(() => {
        disposed = true
      })
      void import('./debug/entry').then(({ registerDebug }) => {
        if (!disposed) {
          registerDebug(ctx)
        }
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
      data: {
        path: '/accounts',
        label: '账号',
        codicon: 'account',
        activity: $loginActivity
      } satisfies SidebarNavContribution
    })
    ctx.register({
      id: 'blueprints',
      area: CRON_BLUEPRINTS_AREA,
      title: '运营计划',
      data: {
        render: ({ owner, view }) => <PlanEditor compact={view === 'summary'} ctx={ctx} owner={owner} />,
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
      render: () => <LegacyPage />
    })
    ctx.registerSettingsPage({
      id: 'settings',
      title: '自动运营',
      render: () => <Button onClick={() => host.navigate('/cron?tab=plan')}>打开运营计划设置</Button>
    })
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
