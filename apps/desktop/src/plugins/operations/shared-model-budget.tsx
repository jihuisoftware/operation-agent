import { Button, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import { type ModelBudget, ModelBudgetFields } from './model-budget-fields'

interface Snapshot {
  version: number
  config: ModelBudget
  day: string
  usage: { calls: number; tokens: number; pending: number; unknown: number }
}

export function SharedModelBudget({ ctx }: { ctx: PluginContext }) {
  const [open, setOpen] = useState(false)

  return <details className="space-y-3" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer">全部主题共用的模型预算</summary>
    {open && <BudgetEditor ctx={ctx} />}
  </details>
}

function BudgetEditor({ ctx }: { ctx: PluginContext }) {
  const [saved, setSaved] = useState<Snapshot | null>(null)
  const [config, setConfig] = useState<ModelBudget | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let disposed = false
    void ctx.rest<Snapshot>('/model-budget').then(value => {
      if (!disposed) { setSaved(value); setConfig(value.config); setError('') }
    }).catch(reason => { if (!disposed) { setError(String(reason)) } })

    return () => { disposed = true }
  }, [ctx, revision])

  const save = async () => {
    if (!saved || !config) { return }
    setBusy(true); setError(''); setNotice('')

    try {
      const result = await ctx.rest<Snapshot>('/model-budget', { method: 'PUT', body: { version: saved.version, config } })
      setSaved(result); setConfig(result.config); setNotice('共享模型预算已保存')
    } catch (reason) { setError(String(reason)) } finally { setBusy(false) }
  }

  return <div className="space-y-3">
    <p className="text-xs text-muted-foreground">此预算由当前配置空间的全部业务与主题共用，与主题预算同时生效。只有一个主题且尚未单独设置时，共享预算跟随主题。单独保存，不会启动任务，也不会清空当天用量。</p>
    {config && <ModelBudgetFields label="全部主题共享" onChange={setConfig} value={config} />}
    {saved && <p className="text-xs text-muted-foreground">{saved.day}：正常调用 {saved.usage.calls} 次，已确认用量 {saved.usage.tokens.toLocaleString()} Token；{saved.usage.pending} 次尚未返回，{saved.usage.unknown} 次用量未确认。</p>}
    {!saved && !error && <p>正在读取共享预算…</p>}
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    <div className="flex gap-2"><Button disabled={busy || !config} onClick={() => void save()}>保存共享预算</Button><Button disabled={busy} onClick={() => setRevision(value => value + 1)} variant="ghost">重新读取</Button></div>
  </div>
}
