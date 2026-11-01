import { createTaskActivity, host, type PluginContext, ROUTES_AREA, SIDEBAR_NAV_AREA, type SidebarNavContribution } from '@hermes/plugin-sdk'

import { DebugPage } from './panel'

export function registerDebug(ctx: PluginContext) {
  const activity = createTaskActivity(host.state.requestOwner, async owner => {
    const catalog = await ctx.rest<{ runs: { state: string }[] }>('/debug', { owner, timeoutMs: 10000 })

    return { running: catalog.runs.filter(run => run.state === 'running').length }
  })

  ctx.register({ id: 'debug', area: ROUTES_AREA, title: '任务调试', data: { path: '/operations-debug' }, render: () => <DebugPage ctx={ctx} /> })
  ctx.register({ id: 'debug-nav', area: SIDEBAR_NAV_AREA, data: { path: '/operations-debug', label: '任务调试（开发）', codicon: 'debug-alt', activity } satisfies SidebarNavContribution })
}
