import { createTaskActivity, host, type PluginContext, ROUTES_AREA, SIDEBAR_NAV_AREA, type SidebarNavContribution } from '@hermes/plugin-sdk'
import type { ReactNode } from 'react'

import { DebugPage } from './panel'

export function registerDebug(ctx: PluginContext, wrap: (page: (scoped: PluginContext) => ReactNode) => ReactNode) {
  const activity = createTaskActivity(host.state.requestOwner, async owner => {
    const catalog = await ctx.rest<{ items: { debug_running: number }[] }>('/workspaces/summary', { owner, timeoutMs: 10000 })

    return { running: catalog.items.reduce((total, item) => total + item.debug_running, 0) }
  })

  ctx.register({ id: 'debug', area: ROUTES_AREA, title: '任务调试', data: { path: '/operations-debug' }, render: () => wrap(scoped => <DebugPage ctx={scoped} />) })
  ctx.register({ id: 'debug-nav', area: SIDEBAR_NAV_AREA, data: { path: '/operations-debug', label: '任务调试（开发）', codicon: 'debug-alt', activity } satisfies SidebarNavContribution })
}
