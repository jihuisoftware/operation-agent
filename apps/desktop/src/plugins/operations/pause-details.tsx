import { Button, host, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'

import { moduleLabels } from './blueprint-types'

export interface PauseOrigin {
  cause_run_id?: string
  cause_started_at?: string
  cause_business_id?: string
  cause_topic_id?: string
  error?: string
}

export function PauseOriginLink({ pause }: { pause?: PauseOrigin }) {
  if (!pause?.cause_run_id && !pause?.cause_started_at) { return null }
  const query = new URLSearchParams({ run: pause.cause_run_id || '' })

  if (pause.cause_business_id && pause.cause_topic_id) {
    query.set('business_id', pause.cause_business_id); query.set('topic_id', pause.cause_topic_id)
  }

  return <span className="text-xs text-muted-foreground">
    {pause.cause_started_at && `原始发生时间：${new Date(pause.cause_started_at).toLocaleString()} `}
    <Button onClick={() => host.navigate(`/operations-interruption?${query}`)} variant="link">查看原始任务</Button>
  </span>
}

interface SourceRun { id: string; stage: string; started: string; state: string; detail: string; pause?: PauseOrigin }

export function PauseDetailsPage({ ctx }: { ctx: PluginContext }) {
  const [params] = useSearchParams()
  const identity = params.get('run') || ''
  const [record, setRecord] = useState<SourceRun | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let disposed = false
    setRecord(null); setError('')
    void ctx.rest<SourceRun>(`/runs/${encodeURIComponent(identity)}/detail`).then(value => {
      if (!disposed) { setRecord(value) }
    }, reason => { if (!disposed) { setError(String(reason)) } })

    return () => { disposed = true }
  }, [ctx, identity])

  return <section className="space-y-4 p-4">
    <h1>原始执行记录</h1>
    {error && <p role="alert">{error}</p>}
    {record ? <><p>{moduleLabels[record.stage] || record.stage} · {new Date(record.started).toLocaleString()} · {record.state}</p>
      <p className="whitespace-pre-wrap">{record.detail}</p>
      {record.pause && <p>{record.pause.error}</p>}
      <p>此页仅查看原始记录；账号检查通过不会自动恢复暂停任务。</p></> : !error && <p>正在加载…</p>}
    <Button onClick={() => host.navigate('/cron?tab=history')}>返回任务记录</Button>
  </section>
}
