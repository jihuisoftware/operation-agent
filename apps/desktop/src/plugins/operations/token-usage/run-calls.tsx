import { Button, type PluginContext } from '@hermes/plugin-sdk'
import { useState } from 'react'

import type { RecordRow } from '../types'

import { CallDetailToggle } from './call-detail'
import { number, statuses, useUsage } from './data'
import type { Page, UsageCall } from './types'

export function RunCallList({ ctx, runs = [] }: { ctx: PluginContext; runs?: RecordRow[] }) {
  return runs.map(row => <RunCalls ctx={ctx} key={row.id} run={String(row.id)} />)
}

export function RunCalls({ ctx, run }: { ctx: PluginContext; run: string }) {
  const [open, setOpen] = useState(false)

  return <details onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer">模型调用 · {run}</summary>
    {open && <RunRequests ctx={ctx} run={run} />}
  </details>
}

function RunRequests({ ctx, run }: { ctx: PluginContext; run: string }) {
  const [cursor, setCursor] = useState('')
  const { data, error, retry } = useUsage<Page<UsageCall>>(ctx, `/usage/tasks/${encodeURIComponent(run)}/calls?all_time=1&cursor=${encodeURIComponent(cursor)}`)

  return <div className="space-y-3 py-3">
    {error && <p role="alert">读取模型调用失败：{error}<Button onClick={retry} variant="ghost">重试</Button></p>}
    {!data && !error && <p role="status">正在读取模型调用…</p>}
    {data?.items.length === 0 && <p>没有模型调用记录；此任务可能未使用模型，或历史用量未保存。</p>}
    {data?.items.map(call => <div key={call.id}><p>{call.model} / {call.provider} · {statuses[call.state] || call.state} · {number(call.total_tokens)} Token</p><CallDetailToggle ctx={ctx} identity={call.id} /></div>)}
    {cursor && <Button onClick={() => setCursor('')} variant="ghost">返回首批调用</Button>}
    {data?.cursor && <Button onClick={() => setCursor(data.cursor!)} variant="ghost">下一批调用</Button>}
  </div>
}
