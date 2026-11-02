import { Button, CopyButton, type CronBlueprintOwner, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useMemo, useState } from 'react'

import { type OperationScope, scopedContext, type WorkspaceTopic } from './workspace-state'

interface HistoryItem { table: string; id: string; record: Record<string, unknown> }

export function WorkspaceHistory({ ctx, owner, scope, topics }: { ctx: PluginContext; owner: CronBlueprintOwner; scope: OperationScope; topics: WorkspaceTopic[] }) {
  const api = useMemo(() => scopedContext(ctx, owner, scope), [ctx, owner, scope])
  const [source, setSource] = useState('')
  const [rows, setRows] = useState<HistoryItem[]>([])
  const [assigned, setAssigned] = useState<unknown[]>([])
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let disposed = false
    setRows([])
    void api.rest<{ items: unknown[] }>('/workspaces/history').then(result => { if (!disposed) { setAssigned(result.items) } }).catch(reason => { if (!disposed) { setMessage(String(reason)) } })

    if (source) {
      void api.rest<{ items: HistoryItem[] }>(`/workspaces/history/${encodeURIComponent(source)}`).then(result => { if (!disposed) { setRows(result.items) } }).catch(reason => { if (!disposed) { setMessage(String(reason)) } })
    }

    return () => { disposed = true }
  }, [api, source, revision])

  return <div className="space-y-2">
    <p>手动归属保留原记录及规则快照，不启动任务、不恢复发送。公开来源需要在资料页另行引用。</p>
    <select aria-label="历史分区" className="w-full rounded border bg-background p-2" onChange={e => setSource(e.target.value)} value={source}><option value="">选择已归档分区</option>{topics.filter(t => t.business_id === scope.business_id && t.archived).map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select>
    {message && <p role="status">{message}</p>}
    <div className="max-h-64 overflow-auto">{rows.map(row => <details className="border-b py-2" key={`${row.table}:${row.id}`}><summary>{String(row.record.kind || row.record.stage || row.table)} · {row.id.slice(0, 12)}</summary><pre className="max-h-40 overflow-auto whitespace-pre-wrap">{JSON.stringify(row.record, null, 2)}</pre><CopyButton label="复制历史记录" text={JSON.stringify(row.record, null, 2)} /><Button disabled={busy || topics.some(t => t.id === scope.topic_id && t.archived)} onClick={async () => {
      setBusy(true)

      try { await api.rest('/workspaces/history', { method: 'POST', body: { source_topic_id: source, table: row.table, record_id: row.id } }); setMessage('已归属到当前主题，原始历史保持可追溯。'); setRevision(value => value + 1) } catch (reason) { setMessage(String(reason)) } finally { setBusy(false) }
    }}>归属到当前主题</Button></details>)}</div>
    <details><summary>已归属到此主题的历史 · {assigned.length}</summary><pre className="max-h-64 overflow-auto whitespace-pre-wrap">{JSON.stringify(assigned, null, 2)}</pre><CopyButton label="复制已归属历史" text={JSON.stringify(assigned, null, 2)} /></details>
  </div>
}
