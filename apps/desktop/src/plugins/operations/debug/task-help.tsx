import { Button, host } from '@hermes/plugin-sdk'

import { LiveViewButton } from '../live-view-button'

import { BrowserCheck } from './browser-check'
import { hasExternalActions } from './quick-selection'
import type { Api } from './task-evidence'
import { guides } from './task-guide'

export function TaskPlan({ task }: { task: string }) {
  const guide = guides[task]

  if (!guide) { return null }

  return <><p>{guide.purpose}</p><section className="space-y-2"><h2 className="font-semibold">预期流程（实际执行见下方时间线）</h2>
    <ol className="list-inside list-decimal space-y-1">{guide.stages.map(stage => <li key={stage}>{stage}</li>)}</ol></section></>
}

export function TaskHelp({ task, busy, version, browserCheck, api }: { task: string; busy: boolean; version?: number; browserCheck?: boolean; api: Api }) {
  const guide = guides[task]

  if (!guide) { return null }

  return <section className="space-y-2"><h2 className="font-semibold">人工检查与处理</h2>
    <ul className="list-inside list-disc space-y-1">{guide.checks.map(check => <li key={check}>{check}</li>)}</ul>
    <Button onClick={() => host.navigate(guide.path)} variant="outline">{guide.destination}</Button>
    {hasExternalActions([task]) && <><LiveViewButton /><Button onClick={() => host.navigate('/accounts')} variant="ghost">检查登录账号</Button>
      <p className="text-sm text-muted-foreground">需要手动查看网页时，在运营画面中选择“人工接管网页”；处理后结束接管，再手动继续。</p>
      {browserCheck && <BrowserCheck busy={busy} onCheck={() => api('/debug/browser-check', { version, request_id: crypto.randomUUID() })} />}</>}
  </section>
}
