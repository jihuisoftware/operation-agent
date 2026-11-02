import { Button, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import { $workspaces, ownerKey } from './workspace-state'

export function WorkspaceReferences({ ctx }: { ctx: PluginContext }) {
  const owner = useValue(host.state.requestOwner)
  const current = useValue($workspaces)[ownerKey(owner)]
  const [topic, setTopic] = useState('')
  const [rows, setRows] = useState<{ id: string; title: string; summary: string; url: string }[]>([])
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let disposed = false
    setRows([])

    if (topic) {
      void ctx.rest<{ items: typeof rows }>(`/workspaces/references/${encodeURIComponent(topic)}`).then(result => {
        if (!disposed) { setRows(result.items) }
      }).catch(reason => { if (!disposed) { setMessage(String(reason)) } })
    }

    return () => { disposed = true }
  }, [ctx, topic])
  const topics = current?.catalog?.topics.filter(t => t.business_id === current.selected?.business_id && t.id !== current.selected.topic_id) || []

  if (!topics.length) { return null }

  return <details className="rounded border p-3"><summary className="cursor-pointer">引用同业务其他主题的资料</summary>
    <select aria-label="资料所在主题" className="my-2 rounded border bg-background p-2" onChange={e => setTopic(e.target.value)} value={topic}><option value="">选择主题</option>{topics.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select>
    {message && <p role="status">{message}</p>}
    <div className="max-h-72 space-y-2 overflow-auto">{rows.map(row => <div className="flex items-center gap-2 border-b py-2" key={row.id}><div className="min-w-0 flex-1"><p>{row.title || row.url}</p><p className="line-clamp-2 text-xs text-muted-foreground">{row.summary}</p></div><Button disabled={busy} onClick={async () => {
      setBusy(true)

      try { await ctx.rest('/workspaces/reference', { method: 'POST', body: { source_topic_id: topic, source_id: row.id } }); setMessage('已引用，来源素材库刷新后可查看；保留原始出处。') } catch (reason) { setMessage(String(reason)) } finally { setBusy(false) }
    }}>引用</Button></div>)}</div>
  </details>
}
