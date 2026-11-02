import { host, type PluginContext, useValue } from '@hermes/plugin-sdk'

import { PlatformLoginsPanel } from './platform-logins'
import { $workspaces, ownerKey } from './workspace-state'

export function AccountsPage({ ctx }: { ctx: PluginContext }) {
  const owner = useValue(host.state.requestOwner)
  const state = useValue($workspaces)[ownerKey(owner)]
  const account = state?.catalog?.businesses.find(b => b.id === state.selected?.business_id)?.account
  const loginOwner = { ...owner, account_id: account }

  return (
    <section aria-label="账号登录" className="h-full overflow-auto p-5 text-sm">
      <header className="mb-5 space-y-2">
        <h1 className="text-xl font-semibold">账号登录</h1>
        <p className="text-muted-foreground">
          在任务运行前检查常用平台的登录情况。检查或登录只接管网页，采集和分析仍可继续；完成后在运营画面点击结束接管。
        </p>
      </header>
      <PlatformLoginsPanel ctx={ctx} key={JSON.stringify(loginOwner)} owner={loginOwner} />
    </section>
  )
}
