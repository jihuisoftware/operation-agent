import { Button, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

interface Storage {
  settings: { days: number; automatic: boolean }
  database_bytes: number
  reusable_bytes: number
  categories: { kind: string; count: number; bytes: number }[]
}
const labels: Record<string, string> = { browser_step: '网页步骤', browser_evidence: '截图', publication_snapshot: '最终稿快照', manual_conclusion: '人工结论' }
const size = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(2)} MB`

export function EvidenceStorage({ ctx }: { ctx: PluginContext }) {
  const [data, setData] = useState<Storage | null>(null)
  const [days, setDays] = useState(30)
  const [automatic, setAutomatic] = useState(false)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let active = true
    void ctx.rest<Storage>('/evidence-storage').then(next => {
      if (active) { setData(next); setDays(next.settings.days); setAutomatic(next.settings.automatic) }
    }).catch(error => { if (active) { setMessage(String(error)) } })

    return () => { active = false }
  }, [ctx])

  const run = async (cleanup: boolean) => {
    setBusy(true)

    try {
      if (cleanup) {
        const result = await ctx.rest<Storage & { steps_deleted: number; screenshots_deleted: number }>('/evidence-storage/cleanup', { method: 'POST' })
        setData(result)
        setMessage(`已清理 ${result.steps_deleted} 条过期步骤和 ${result.screenshots_deleted} 张截图；未解决异常证据继续保留。`)
      } else {
        await ctx.rest('/evidence-storage', { method: 'PUT', body: { days, automatic } })
        setData(await ctx.rest<Storage>('/evidence-storage'))
        setMessage('保留设置已保存')
      }
    } catch (error) { setMessage(String(error)) }
    finally { setBusy(false) }
  }

  return <details className="space-y-3"><summary className="cursor-pointer">日志与截图存储管理</summary>
    {data && <><p>数据库占用 {size(data.database_bytes)} · 可复用空间 {size(data.reusable_bytes)}</p><div className="flex flex-wrap gap-4">{data.categories.map(row => <p key={row.kind}>{labels[row.kind]}：{row.count} 条 · {size(row.bytes)}</p>)}</div></>}
    <label>保留期限 <select aria-label="证据保留期限" onChange={event => setDays(Number(event.target.value))} value={days}>{[7, 30, 90, 180, 365].map(value => <option key={value} value={value}>{value} 天</option>)}</select></label>
    <label className="block"><input checked={automatic} onChange={event => setAutomatic(event.target.checked)} type="checkbox" />每天自动清理到期记录</label>
    <p className="text-sm text-muted-foreground">仅清理已处理任务的到期网页步骤与无引用截图。未解决异常、最终稿和人工结论继续保留；清理后的数据库空间可复用。</p>
    <div className="flex gap-2"><Button disabled={busy} onClick={() => void run(false)}>保存保留设置</Button><Button disabled={busy || !data || days !== data.settings.days || automatic !== data.settings.automatic} onClick={() => void run(true)}>清理到期记录</Button></div>
    {message && <p role="status">{message}</p>}
  </details>
}
