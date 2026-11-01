import { Badge, Button, Codicon, CopyButton, formatTimestamp } from '@hermes/plugin-sdk'
import { useState } from 'react'

import type { AnalysisApi, AnalysisReport, Metric } from './analysis-types'

function Bars({ title, values }: { title: string; values: Record<string, number> }) {
  const rows = Object.entries(values)
  const maximum = Math.max(1, ...rows.map(([, value]) => value))

  return <figure aria-label={title} className="space-y-3"><figcaption className="font-medium">{title}</figcaption>
    {!rows.length && <p className="text-muted-foreground">暂无可用数据</p>}
    {rows.map(([label, value]) => <div className="grid grid-cols-[minmax(6rem,1fr)_2fr_3rem] items-center gap-3 text-xs" key={label}><span className="truncate" title={label}>{label}</span><div className="h-2 bg-muted"><div className="h-2 bg-primary" style={{ width: `${value / maximum * 100}%` }} /></div><span>{value}</span></div>)}
  </figure>
}

function MetricCard({ metric }: { metric: Metric }) {
  return <article className="space-y-2 rounded-lg bg-muted/30 p-4">
    <div className="flex items-center justify-between gap-2"><h4>{metric.name}</h4><Badge>{metric.visibility === 'public' ? '可公开' : '内部'}</Badge></div>
    <p className="text-2xl font-semibold tabular-nums">{metric.value ?? '缺失'} <span className="text-xs font-normal">{metric.unit}</span></p>
    <p className="text-xs text-muted-foreground">较前期：{metric.growth_percent != null ? `${Number(metric.growth_percent).toFixed(1)}%` : '不可比较'} · 样本 {metric.samples ?? '未知'} · 缺失 {metric.missing ?? '未知'}</p>
    <details className="text-xs"><summary>口径与每日数据</summary><p>{metric.definition}</p><p>前期值：{metric.previous ?? '缺失'}</p>{Object.entries(metric.trend || {}).map(([day, value]) => <p key={day}>{day}：{value ?? '缺失'}</p>)}</details>
  </article>
}

export function downloadAnalysis(content: string, name: string, mime: string) {
  const url = URL.createObjectURL(new Blob([content], { type: mime }))
  const link = document.createElement('a')
  link.href = url; link.download = name; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function AnalysisResults({ report, view, api, onSource }: { report: AnalysisReport; view: string; api: AnalysisApi; onSource: (id: string) => void }) {
  const [error, setError] = useState('')
  const [publicExport, setPublicExport] = useState(false)

  const exportReport = async (format: string) => {
    try {
      const result = await api<{ content: string; name: string; mime: string }>(`/reports/${report.id}/export?format=${format}&public=${publicExport}`)
      downloadAnalysis(result.content, result.name, result.mime)
    } catch (reason) { setError(String(reason)) }
  }

  const findings = report.findings?.filter(item => item.view === view) || []

  return <section className="space-y-5">
    <header className="space-y-2"><div className="flex flex-wrap items-center gap-2"><Badge variant={report.current ? 'success' : 'warn'}>{report.current ? '当前范围有效' : '历史结果 · 不供自动生产引用'}</Badge><span className="text-xs text-muted-foreground">{formatTimestamp(report.created)} · 模型调用 {report.model_calls}</span></div><p>{report.detail}</p><p className="text-xs text-muted-foreground">{report.window.start}～{report.window.end} · 前期 {report.window.previous_start}～{report.window.previous_end}</p></header>
    {report.sources && <>
      <div className="grid gap-3 sm:grid-cols-3">{[['read', '去重可读来源'], ['organized', '已整理资料'], ['failed', '读取失败']].map(([key, label]) => <div className="space-y-2 bg-muted/30 p-4" key={key}><Codicon name="graph" /><p>{label}</p><strong className="text-2xl">{report.sources!.counts[key] || 0}</strong><p className="text-xs text-muted-foreground">前期 {report.sources!.previous[key] || 0} 条</p></div>)}</div>
      <p className="text-xs text-muted-foreground">采集量是样本覆盖，不代表行业规模。不同币种、平台及指标口径分别展示。</p>
      <div className="grid gap-8 md:grid-cols-2"><Bars title="来源趋势" values={report.sources.trend} /><Bars title="资料分类" values={report.sources.categories} /><Bars title="需求与主题关键词" values={report.sources.keywords} /><Bars title="来源站点覆盖" values={report.sources.platforms} /></div>
      <h3 className="font-medium">业务指标</h3><div className="grid gap-3 md:grid-cols-2">{report.metrics?.map(metric => <MetricCard key={metric.id} metric={metric} />)}</div>
      {!report.metrics?.length && <p className="text-muted-foreground">未导入当前主题业务数据。</p>}
      <h3 className="font-medium">可获取的账号运营指标</h3><div className="grid gap-3 md:grid-cols-2">{report.operational_metrics?.map(metric => <MetricCard key={metric.id} metric={metric} />)}</div>
      {!report.operational_metrics?.length && <p className="text-muted-foreground">未获取平台指标，不推断增长或转化。</p>}
    </>}
    {report.findings && <>
      {!findings.length && <p className="bg-muted/30 p-4">当前视角证据不足，尚未形成可用结论。</p>}
      {findings.map((finding, index) => <article className="space-y-3 border-b pb-4" key={index}>
        <div className="flex gap-2"><Badge>{finding.dimension}</Badge><Badge>{finding.visibility === 'public' ? '可公开' : '内部经营参考'}</Badge></div><h3 className="font-medium">{finding.title}</h3><p>{finding.text}</p>
        <details><summary className="cursor-pointer">依据、适用范围与待核实事项</summary><div className="mt-3 space-y-2 text-xs"><p>适用范围：{finding.scope}</p><p>反向证据：{finding.counter}</p><p>待核实：{finding.unknowns}</p>{finding.evidence_ids.map(id => { const evidence = report.evidence.find(e => e.id === id);

          return <div key={id}><p>{evidence?.title || evidence?.name || id}</p>{evidence?.url && <Button onClick={() => onSource(id)} size="sm" variant="outline">查看原始图文</Button>}{evidence?.url && <p className="break-all select-text">{evidence.url}<CopyButton text={evidence.url} /></p>}<p>{evidence?.summary || evidence?.definition}</p>{evidence?.value != null && <p>{evidence.value}</p>}</div> })}</div></details>
      </article>)}
      {['趋势', '需求', '竞争', '产品价格', '机会', '风险'].filter(d => !findings.some(f => f.dimension === d)).map(d => <p className="text-xs text-muted-foreground" key={d}>{d}：证据不足</p>)}
    </>}
    <div className="flex flex-wrap items-center gap-2"><Button onClick={() => setPublicExport(!publicExport)} variant="outline">导出范围：{publicExport ? '可公开材料' : '内部报告'}</Button><Button onClick={() => void exportReport('markdown')} variant="outline">导出 Markdown</Button>{report.sources && <Button onClick={() => void exportReport('csv')} variant="outline">导出图表 CSV</Button>}</div>
    {error && <p className="text-destructive" role="alert">{error}</p>}
  </section>
}
