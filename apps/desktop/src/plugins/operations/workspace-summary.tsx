import { Badge, Button, Codicon, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import { $workspaces, chooseScope, ownerKey } from './workspace-state'

interface SummaryRow {
  id: string; business_id: string; name: string; enabled: boolean; paused: boolean; archived: number
  counts: Record<string, number>; running: { stage: string; detail: string }[]; latest?: { state: string; detail: string }
}

export function WorkspaceSummary({ ctx }: { ctx: PluginContext }) {
  const owner = useValue(host.state.requestOwner)
  const current = useValue($workspaces)[ownerKey(owner)]
  const [all, setAll] = useState(false)
  const [rows, setRows] = useState<SummaryRow[]>([])
  const [error, setError] = useState('')
  useEffect(() => {
    let disposed = false

    const refresh = async () => {
      try {
        const result = await ctx.rest<{ items: SummaryRow[] }>('/workspaces/summary')

        if (!Array.isArray(result.items)) { throw new Error('业务汇总接口不可用，请更新 Server') }

        if (!disposed) { setRows(result.items); setError('') }
      } catch (reason) { if (!disposed) { setError(String(reason)) } }
    }

    void refresh()
    const timer = setInterval(() => void refresh(), 10000)

    return () => { disposed = true; clearInterval(timer) }
  }, [ctx])

  return <details className="space-y-3 rounded border p-3"><summary className="cursor-pointer font-medium"><Codicon name="organization" /> 业务运行汇总</summary>
    <Button aria-pressed={all} onClick={() => setAll(!all)} size="sm" variant="ghost">{all ? '全部业务' : '当前业务'} · 点击切换范围</Button>
    {error && <p className="text-destructive" role="alert">{error}</p>}
    <div className="grid gap-3 sm:grid-cols-2">{rows.filter(r => all || r.business_id === current?.selected?.business_id).map(row => <article className="space-y-2 rounded border p-3" key={row.id}>
      <div className="flex items-center justify-between gap-2"><span>{current?.catalog?.businesses.find(b => b.id === row.business_id)?.name} / {row.name}</span><Badge variant={row.running.length ? 'success' : 'muted'}>{row.archived ? '已归档' : row.running.length ? '执行中' : row.paused ? '已暂停' : row.enabled ? '已启用' : '待配置'}</Badge></div>
      <p className="flex gap-4 text-muted-foreground"><span><Codicon name="library" /> {row.counts.source || 0} 条资料</span><span><Codicon name="file-media" /> {row.counts.content || 0} 篇内容</span><span><Codicon name="report" /> {row.counts.report || 0} 份日报</span></p>
      {row.running.map(run => <p key={run.stage}><Codicon name="loading" spinning /> {run.detail}</p>)}
      <Button onClick={() => chooseScope(owner, { business_id: row.business_id, topic_id: row.id })} size="sm" variant="ghost">查看此主题</Button>
    </article>)}</div>
  </details>
}
