import { Button, Codicon, formatTimestamp, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useMemo, useState } from 'react'

import { dimensions, number, periods, queryString, timestamp, useUsage } from './data'
import { UsageTasks } from './tasks'
import type { Summary } from './types'
import { purposeLabel, TokenMetrics, UsageTrend } from './visuals'

export function TokenUsagePage({ ctx }: { ctx: PluginContext }) {
  const owner = useValue(host.state.requestOwner)
  const bound = useMemo<PluginContext>(() => ({ ...ctx, rest: (path, options) => ctx.rest(path, { ...options, owner }) }), [ctx, owner])

  return <OwnedUsage ctx={bound} key={JSON.stringify(owner)} />
}

function OwnedUsage({ ctx }: { ctx: PluginContext }) {
  const [period, setPeriod] = useState('day')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [dimension, setDimension] = useState('module')
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')
  const query = queryString(period, filters)
  const { data, error, retry } = useUsage<Summary>(ctx, '/usage/summary?' + query)
  const { data: choices } = useUsage<Summary>(ctx, '/usage/summary?' + queryString(period))
  const rows = data?.groups[dimension] || []

  async function download() {
    if (!data) { return }
    setExporting(true); setExportError('')

    try {
      const result = await ctx.rest<{ csv: string }>(`/usage/export?${query}&until=${data.until}&transport=json`, { timeoutMs: 60000 })
      const url = URL.createObjectURL(new Blob([result.csv], { type: 'text/csv;charset=utf-8' }))
      const link = document.createElement('a')
      link.href = url; link.download = 'token-usage.csv'; link.click(); URL.revokeObjectURL(url)
    } catch (reason) { setExportError(String(reason)) } finally { setExporting(false) }
  }

  return <main aria-label="Token 用量" className="@container h-full space-y-5 overflow-auto p-5 text-sm">
    <header className="flex flex-wrap items-center gap-3"><Codicon name="pulse" /><h1 className="mr-auto text-xl font-semibold">Token 用量</h1><Button onClick={retry} variant="ghost">刷新</Button><Button disabled={!data || exporting} onClick={() => void download()} variant="outline">{exporting ? '正在导出…' : '导出 CSV'}</Button></header>
    <p className="text-xs text-muted-foreground">当前 Profile 全部业务与 AI 助手；准确用量在模型返回回执后更新。每 5 秒刷新。</p>
    <div aria-label="时间范围" className="flex flex-wrap gap-2">{Object.entries(periods).map(([value, label]) => <Button aria-pressed={period === value} key={value} onClick={() => setPeriod(value)} variant={period === value ? 'secondary' : 'ghost'}>{label}</Button>)}</div>
    <div className="flex flex-wrap gap-3">{Object.entries(dimensions).filter(([key]) => key !== 'purpose').map(([key, label]) => <label className="grid gap-1 text-xs" key={key}>{label}<select aria-label={`筛选${label}`} className="max-w-56 rounded border bg-background p-2" onChange={event => setFilters(previous => ({ ...previous, [key]: event.target.value, ...(key === 'business' ? { topic: '' } : {}) }))} value={filters[key] || ''}><option value="">全部</option>{choices?.groups[key].map(item => <option key={item.id} value={item.id || '__unassigned__'}>{key === 'module' ? purposeLabel(item.id) : item.label}{key === 'topic' && `（${item.id.slice(0, 6)}）`}</option>)}</select></label>)}<Button onClick={() => setFilters({})} variant="ghost">清除筛选</Button></div>
    {error && <p role="alert">读取失败，已有数据可能过期：{error}</p>}{exportError && <p role="alert">导出失败：{exportError}</p>}
    {!data && !error && <p role="status">正在统计用量…</p>}
    {data && <><TokenMetrics totals={data.totals} /><p className="text-xs text-muted-foreground">{data.totals.running || 0} 次调用统计中 · {data.totals.unknown || 0} 次用量未知（未按零计入） · 更新于 {formatTimestamp(timestamp(data.until))}{data.partial_history && ` · 仅包含 ${formatTimestamp(timestamp(data.since))} 开始记录后的数据`}</p>
      <UsageTrend data={data} /><section className="space-y-3"><header className="flex items-center gap-3"><h2 className="font-semibold">分类消耗</h2><select aria-label="统计维度" className="rounded border bg-background p-2" onChange={event => setDimension(event.target.value)} value={dimension}>{Object.entries(dimensions).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></header>
        <div className="max-h-80 space-y-3 overflow-auto">{rows.map(row => <div key={row.id}><div className="flex justify-between gap-3"><span>{['module', 'purpose'].includes(dimension) ? purposeLabel(row.id) : row.label}</span><span>{number(row.total_tokens)} · {data.totals.total_tokens ? (row.total_tokens / data.totals.total_tokens * 100).toFixed(1) : '0'}%</span></div><progress aria-label={`${row.label}消耗占比`} className="h-1 w-full accent-primary" max={Math.max(1, data.totals.total_tokens)} value={row.total_tokens} /></div>)}{!rows.length && <p>暂无模型调用</p>}</div>
      </section><UsageTasks ctx={ctx} key={query} query={query} /><p className="text-xs text-muted-foreground">总 Token 包含输入（含缓存）与输出；推理已包含在输出中，不重复累加。文件本地解析不产生 Token，混合图文调用不拆分估算。</p></>}
  </main>
}
