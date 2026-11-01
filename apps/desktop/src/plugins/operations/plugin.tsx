import {
  CRON_BLUEPRINTS_AREA,
  type CronBlueprintContribution,
  type HermesPlugin,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  type SidebarNavContribution,
  TITLEBAR_AREAS
} from '@hermes/plugin-sdk'
import { createRoot } from 'react-dom/client'

import { AccountsPage } from './accounts'
import { BlueprintLibrary } from './blueprint-library'
import { $loginActivity } from './login-activity'
import { $showOperationsBrowser } from './state'
import { UpcomingOperations } from './upcoming'
import { Workbench } from './workbench'
import { OperationsWorker } from './worker'

declare const __OPERATIONS_DEBUG__: boolean

export default {
  id: 'operations',
  name: '每日自动运营',
  description: '目标、信息来源、规则执行与每日总结',
  register(ctx) {
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
      render: () => (
        <button
          className="px-2 text-xs"
          onClick={() => $showOperationsBrowser.set(!$showOperationsBrowser.get())}
          title="显示或隐藏自动运营内嵌网页"
        >
          运营画面
        </button>
      )
    })
    ctx.register({
      id: 'workbench',
      area: ROUTES_AREA,
      title: '自动运营',
      data: { path: '/operations' },
      render: () => <Workbench ctx={ctx} />
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
