import { Button, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useState } from 'react'

import type { RecordRow } from './types'
import { $workspaces, ownerKey } from './workspace-state'

export function InboxTransfer({ ctx, row, saved, failed }: { ctx: PluginContext; row: RecordRow; saved: () => Promise<unknown>; failed: (message: string) => void }) {
  const owner = useValue(host.state.requestOwner)
  const current = useValue($workspaces)[ownerKey(owner)]
  const account = current?.catalog?.businesses.find(b => b.id === current.selected?.business_id)?.account
  const businesses = current?.catalog?.businesses.filter(b => !b.archived && b.account === account) || []
  const targets = current?.catalog?.topics.filter(t => !t.archived && t.id !== current.selected?.topic_id && businesses.some(b => b.id === t.business_id)) || []
  const [target, setTarget] = useState('')
  const [busy, setBusy] = useState(false)

  if (row.state !== 'needs_review' || !targets.length) { return null }

  return <div className="flex flex-wrap items-center gap-2 py-2"><span className="max-w-64 truncate">{String(row.text || row.id)}</span>
    <select aria-label="转交主题" className="rounded border bg-background p-2" onChange={e => setTarget(e.target.value)} value={target}><option value="">选择共用账号的主题</option>{targets.map(t => <option key={t.id} value={t.id}>{businesses.find(b => b.id === t.business_id)?.name} / {t.name}</option>)}</select>
    <Button disabled={busy || !target} onClick={async () => {
      const topic = targets.find(t => t.id === target)

      if (!topic) { return }
      setBusy(true)

      try { await ctx.rest('/workspaces/transfer-inbox', { method: 'POST', body: { id: row.id, business_id: topic.business_id, topic_id: topic.id } }); await saved() } catch (reason) { failed(String(reason)) } finally { setBusy(false) }
    }}>转交待处理事项</Button>
  </div>
}
