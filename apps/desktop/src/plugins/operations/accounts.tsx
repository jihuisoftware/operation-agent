import { host, type PluginContext, useValue } from '@hermes/plugin-sdk'

import { PlatformLoginsPanel } from './platform-logins'

export function AccountsPage({ ctx }: { ctx: PluginContext }) {
  const owner = useValue(host.state.requestOwner)

  return (
    <section aria-label="账号登录" className="h-full overflow-auto p-5 text-sm">
      <header className="mb-5 space-y-2">
        <h1 className="text-xl font-semibold">账号登录</h1>
        <p className="text-muted-foreground">
          在任务运行前检查常用平台的登录情况。检查或登录会暂停当前运营计划，完成后请回到定时任务恢复计划。
        </p>
      </header>
      <PlatformLoginsPanel ctx={ctx} key={JSON.stringify(owner)} owner={owner} />
    </section>
  )
}
