import { type HermesPlugin, ROUTES_AREA, TITLEBAR_AREAS } from '@hermes/plugin-sdk'
import { createRoot } from 'react-dom/client'

import { $showOperationsBrowser } from './state'
import { Workbench } from './workbench'
import { OperationsWorker } from './worker'

export default {
  id: 'operations',
  name: '每日自动运营',
  description: '目标、信息来源、规则执行与每日总结',
  register(ctx) {
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
