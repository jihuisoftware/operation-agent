import { Button, host, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import { SourceLimitField } from './source-limit-field'

interface Snapshot { version: number; limit: number; day: string; used: number; shared_limit: number | null; shared_used: number | null; shared_day: string | null; remaining: number }
interface Props { ctx: PluginContext }

export function CollectionSettings({ ctx }: Props) {
  const [saved, setSaved] = useState<Snapshot | null>(null), [limit, setLimit] = useState<number | null>(null)
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState(''), [reload, setReload] = useState(0)
  useEffect(() => {
    let live = true
    setSaved(null); setLimit(null); setError(''); setNotice('')
    void ctx.rest<Snapshot>('/collection-budget').then(value => { if (live) { setSaved(value); setLimit(value.limit) } }).catch(reason => { if (live) { setError(String(reason)) } })

    return () => { live = false }
  }, [ctx, reload])

  const save = async () => {
    if (!saved || limit === null) { return }
    setBusy(true); setError(''); setNotice('')

    try {
      const value = await ctx.rest<Snapshot>('/collection-budget', { method: 'PUT', body: { version: saved.version, limit } })
      setSaved(value); setLimit(value.limit); setNotice(`每日采集上限已保存为 ${value.limit.toLocaleString()} 次，当天已用次数保留。`)
    } catch (reason) { setError(String(reason)) } finally { setBusy(false) }
  }

  return <section aria-label="采集设置" className="space-y-4 p-4">
    <h2 className="font-semibold">当前主题的采集设置</h2>
    {limit !== null && <fieldset disabled={busy}><SourceLimitField onChange={setLimit} value={limit} /></fieldset>}
    {saved && <div className="space-y-1 text-sm">
      <p>{saved.day}：本主题已用 {saved.used.toLocaleString()} / {saved.limit.toLocaleString()} 次，剩余可用 {saved.remaining.toLocaleString()} 次。</p>
      {saved.shared_limit !== null && <p>当前配置空间的全部主题共享额度（{saved.shared_day}）：{saved.shared_used?.toLocaleString()} / {saved.shared_limit.toLocaleString()} 次。</p>}
      {saved.shared_limit !== null && limit !== null && saved.shared_limit < limit && <p>还会受到上述共享额度约束；提高本主题上限不会自动提高多主题共享额度。</p>}
      {limit !== null && limit <= saved.used && <p>新上限不高于当天已用量，保存后今天将不再新增读取。</p>}
    </div>}
    <p className="text-xs text-muted-foreground">仅修改当前业务、主题的采集额度。保存会更新运营规则，使用旧规则的任务可能停止；不会清空已采集资料或当天用量，也不会发起新批次。</p>
    {!saved && !error && <p role="status">正在读取采集设置…</p>}
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    <div className="flex flex-wrap gap-2"><Button disabled={busy || !saved || limit === null || limit < 100 || limit > 10000 || limit === saved.limit} onClick={() => void save()}>保存采集上限</Button><Button disabled={busy} onClick={() => setReload(value => value + 1)} variant="outline">重新读取</Button><Button onClick={() => host.navigate('/cron?tab=plan')} variant="ghost">打开完整运营计划</Button></div>
  </section>
}
