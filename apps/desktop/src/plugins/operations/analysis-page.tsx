import { Badge, Button, Codicon, CopyButton, type CronBlueprintOwner, formatTimestamp, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useEffect, useMemo, useState } from 'react'

import { AnalysisResults } from './analysis-results'
import { AnalysisSettings } from './analysis-settings'
import type { AnalysisApi, AnalysisCatalog, AnalysisReport } from './analysis-types'
import { BusinessDatasets } from './business-datasets'
import { SourceDetail } from './source-library'

export function AnalysisPage({ ctx, stage }: { ctx: PluginContext; stage: 'analytics' | 'industry' }) {
  const owner = useValue(host.state.requestOwner)

  return <OwnedAnalysisPage ctx={ctx} key={`${JSON.stringify(owner)}:${stage}`} owner={owner} stage={stage} />
}

export function OwnedAnalysisPage({ ctx, owner, stage }: { ctx: PluginContext; owner: CronBlueprintOwner; stage: 'analytics' | 'industry' }) {
  const [data, setData] = useState<AnalysisCatalog | null>(null)
  const [tab, setTab] = useState(stage === 'analytics' ? 'overview' : 'content')
  const [selected, setSelected] = useState('')
  const [sourceId, setSourceId] = useState<string | null>(null)
  const boundCtx = useMemo<PluginContext>(() => ({ ...ctx, rest: (path, options) => ctx.rest(path, { ...options, owner }) }), [ctx, owner])
  const [report, setReport] = useState<AnalysisReport | null>(null)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [revision, setRevision] = useState(0)
  const [logId, setLogId] = useState('')
  const [log, setLog] = useState<{ run: unknown; events: unknown[]; errors: unknown[] } | null>(null)
  const api = useMemo<AnalysisApi>(() => (path, body) => ctx.rest(`/analysis${path}`, { owner, method: body ? 'POST' : 'GET', body, timeoutMs: body ? 1_800_000 : 15000 }), [ctx, owner])
  const refresh = () => setRevision(v => v + 1)
  useEffect(() => {
    let disposed = false
    let busy = false

    const load = async () => {
      if (busy) { return }
      busy = true

      try {
        const value = await api<AnalysisCatalog>('')

        if (!disposed) { setData(value) }
      }
      catch (reason) { if (!disposed) { setError(String(reason)) } }
      finally { busy = false }
    }

    void load()
    const timer = setInterval(() => void load(), 5000)

    return () => { disposed = true; clearInterval(timer) }
  }, [api, revision])
  const reports = data?.reports.filter(r => r.kind === `${stage}_report`) || []
  const reportId = selected || reports[0]?.id
  useEffect(() => {
    let disposed = false
    setReport(null)

    if (reportId) {
      void api<AnalysisReport>(`/reports/${reportId}`).then(value => { if (!disposed) { setReport(value) } }).catch(reason => { if (!disposed) { setError(String(reason)) } })
    }

    return () => { disposed = true }
  }, [api, reportId, revision])

  useEffect(() => {
    if (!logId) { return }
    let disposed = false
    let busy = false

    const loadLog = async () => {
      if (busy) { return }
      busy = true

      try {
        const next = await api<{ run: unknown; events: unknown[]; errors: unknown[] }>(`/logs/${logId}`)

        if (!disposed) { setLog(next) }
      }
      catch (reason) { if (!disposed) { setError(String(reason)) } }
      finally { busy = false }
    }

    void loadLog()
    const timer = setInterval(() => void loadLog(), 3000)

    return () => { disposed = true; clearInterval(timer) }
  }, [api, logId])

  const act = async (fn: () => Promise<void>) => {
    setPending(true); setError('')

    try { await fn(); refresh() } catch (reason) { setError(String(reason)) } finally { setPending(false) }
  }

  const tabs = stage === 'analytics' ? [['overview', '分析概览'], ['business', '业务数据'], ['history', '历史结果']] : [['content', '内容运营'], ['market', '市场经营'], ['history', '证据与历史']]
  const title = stage === 'analytics' ? '数据分析' : '行业分析'

  return <main aria-label={title} className="h-full overflow-auto p-5 text-sm"><div className="mx-auto max-w-6xl space-y-5">
    <header className="flex flex-wrap items-center justify-between gap-3"><h1 className="flex items-center gap-2 text-xl font-semibold"><Codicon name={stage === 'analytics' ? 'graph' : 'globe'} />{title}</h1><div className="flex gap-2"><Button disabled={pending || !data} onClick={() => void act(async () => { await api(`/run/${stage}`, { version: data!.version, request_id: crypto.randomUUID() }); setSelected('') })}>立即分析</Button><Button onClick={refresh} variant="ghost">刷新</Button></div></header>
    {error && <p className="text-destructive" role="alert">{error}</p>}
    {!data && !error && <p>正在读取分析数据…</p>}
    {data && <>
      {!data.policy.modules[stage] && <p className="text-muted-foreground">该模块尚未启用。<Button onClick={() => host.navigate('/cron')} variant="link">前往运营蓝图配置</Button></p>}
      <AnalysisSettings api={api} data={data} failed={setError} key={data.settings.version} saved={refresh} />
      <nav aria-label={`${title}页签`} className="flex gap-2">{tabs.map(([key, label]) => <Button aria-pressed={tab === key} key={key} onClick={() => setTab(key)} variant={tab === key ? 'secondary' : 'ghost'}>{label}</Button>)}</nav>
      {tab === 'business' ? <BusinessDatasets api={api} data={data} saved={refresh} /> : <>
        {tab === 'history' && <section className="space-y-3"><h2>报告版本</h2>{reports.map(row => <Button className="w-full justify-start" key={row.id} onClick={() => setSelected(row.id)} variant={reportId === row.id ? 'secondary' : 'ghost'}>{formatTimestamp(row.created)} · {row.detail}</Button>)}</section>}
        {report ? <AnalysisResults api={api} key={`${report.id}:${tab}:${revision}`} onSource={setSourceId} report={report} view={tab === 'market' ? 'market' : 'content'} /> : <p className="bg-muted/30 p-5 text-muted-foreground">暂无分析结果。启用模块并执行后，这里会显示统计图表与可追溯结论。</p>}
      </>}
      <section className="space-y-3 border-t pt-4"><h2 className="font-medium">执行过程与记录</h2>
        {data.runs.filter(r => r.stage === stage).map(run => <details className="space-y-2" key={run.id}><summary className="cursor-pointer">{formatTimestamp(run.started)} · {{ running: '正在执行', completed: '完成', needs_attention: '待完善', cancelled: '取消', failed: '失败', skipped: '跳过', interrupted: '中断' }[run.state] || run.state} · {run.detail}</summary><div className="flex gap-2"><Button onClick={() => { setLog(null); setLogId(run.id) }} variant="outline">读取完整过程</Button>{run.state === 'running' && <Button onClick={() => void act(async () => { await api(`/cancel/${run.id}`, {}) })} variant="outline">取消本次分析</Button>}</div></details>)}
        {log && <div className="space-y-2"><div className="flex items-center gap-3"><CopyButton label="复制完整过程" text={JSON.stringify(log, null, 2)} /><span>复制完整过程</span><CopyButton label="只复制错误" text={JSON.stringify(log.errors, null, 2)} /><span>只复制错误</span><Badge>{log.events.length} 条记录</Badge></div><pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs select-text">{JSON.stringify(log, null, 2)}</pre></div>}
      </section>
    </>}
    {sourceId && <SourceDetail ctx={boundCtx} identity={sourceId} key={sourceId} onClose={() => setSourceId(null)} />}
  </div></main>
}
