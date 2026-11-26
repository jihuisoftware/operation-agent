import { Badge, Button, CopyButton, formatTimestamp, type PluginContext } from '@hermes/plugin-sdk'
import { useState } from 'react'

interface Week {
  start: string
  end: string
  attempted: number
  new_per_100: number | null
  relevant_per_100: number | null
  relevant: number
  organization_calls: number
  fixed_not_read_today: number
  keywords: string[]
  legacy_batches: number
  cited_english: number
  cited_unknown_language: number
}

export interface CollectionSummaryData {
  queries?: { query: string; language: string; keyword: string }[]
  english_reason?: string
  new_reads?: number
  rechecks?: number
  changed?: number
  unchanged?: number
  deferred_rechecks?: number
  started: string
  state: string
  succeeded: number
  new: number
  duplicate_content: number
  already_read: number
  failed: number
  not_attempted: number
  retried: number
  used?: number
  limit: number
  search_errors: number
  searches_remaining?: number
  reason?: string
}

export function CollectionSummary({ data, ctx }: { data: CollectionSummaryData; ctx: PluginContext }) {
  const [week, setWeek] = useState<Week | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async () => {
    setBusy(true)
    setError('')

    try {
      setWeek(await ctx.rest<Week>('/sources/collection-report'))
    } catch (reason) {
      setError(String(reason))
    } finally {
      setBusy(false)
    }
  }

  const items = [['读取成功', data.succeeded], ['新资料', data.new], ['正文重复', data.duplicate_content], ['已采集跳过', data.already_read], ['读取失败', data.failed], ['未尝试', data.not_attempted]] as const

  return <section aria-label="最近采集批次" className="space-y-3 rounded-xl bg-muted/20 p-4">
    <div className="flex flex-wrap items-center gap-2"><span className="text-sm font-medium">最近采集 · {formatTimestamp(data.started)}</span><Badge variant="muted">{data.state === 'running' ? '采集中' : data.state === 'interrupted' ? '已中断' : '本批结束'}</Badge></div>
    <dl className="grid grid-cols-3 gap-3 sm:grid-cols-6">{items.map(([label, value]) => <div key={label}><dt className="text-xs text-muted-foreground">{label}</dt><dd className="text-lg font-semibold tabular-nums">{value}</dd></div>)}</dl>
    {data.reason && <p className="text-sm">{data.reason}</p>}
    <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">统计口径与检索进度</summary>
      <p className="mt-2">成功包含新资料与正文重复；重试 {data.retried} 次。失败和重试均消耗读取额度，今日已用 {data.used ?? '待更新'} / {data.limit}。每个链接当天最多尝试三次，额度或重试次数不足计入未尝试。</p>
      <p>检索/订阅异常 {data.search_errors} 次；尚可扩展的查询 {data.searches_remaining ?? 0} 个。分轮扩大搜索结果数量，不保证全平台覆盖。仅已取得的有效正文进入后续整理。</p>
      <p>新链接读取 {data.new_reads ?? '未记录'}，到期复查 {data.rechecks ?? '未记录'}，正文变化 {data.changed ?? '未记录'}，未变 {data.unchanged ?? '未记录'}，延期复查 {data.deferred_rechecks ?? '未记录'}。</p>
      <p>英文检索：{data.english_reason ?? '未记录'}</p>
      {data.queries ? <ul>{data.queries.map(row => <li key={row.query}>{row.language === 'en' ? '英文' : '中文'} · {row.keyword} → {row.query}</li>)}</ul> : <p>实际查询：未记录</p>}
      <CopyButton label="复制采集批次统计" text={() => JSON.stringify(data, null, 2)}>复制采集批次统计</CopyButton>
    </details>
    <Button disabled={busy} onClick={() => void load()} size="sm" variant="outline">{busy ? '正在读取…' : '查看近七日采集成效'}</Button>
    {error && <p role="alert">{error}</p>}
    {week && <div className="text-sm">
      <p>{week.start} 至 {week.end} · 非调试批次读取 {week.attempted} 次，每百次读取新增 {week.new_per_100 ?? '—'} 条。</p>
      <p>去重相关资料 {week.relevant} 条，每百次读取 {week.relevant_per_100 ?? '—'} 条，整理模型调用 {week.organization_calls} 次，选题引用英文原文 {week.cited_english} 条（语言未知 {week.cited_unknown_language} 条）。</p>
      <p>固定网址今日尚未读到 {week.fixed_not_read_today} 个。检索覆盖词：{week.keywords.join('、') || '未记录'}。缺少查询明细的旧批次 {week.legacy_batches} 个。</p>
    </div>}
  </section>
}
