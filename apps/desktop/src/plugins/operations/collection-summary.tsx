import { Badge, CopyButton, formatTimestamp } from '@hermes/plugin-sdk'

export interface CollectionSummaryData {
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

export function CollectionSummary({ data }: { data: CollectionSummaryData }) {
  const items = [['读取成功', data.succeeded], ['新资料', data.new], ['正文重复', data.duplicate_content], ['已采集跳过', data.already_read], ['读取失败', data.failed], ['未尝试', data.not_attempted]] as const

  return <section aria-label="最近采集批次" className="space-y-3 rounded-xl bg-muted/20 p-4">
    <div className="flex flex-wrap items-center gap-2"><span className="text-sm font-medium">最近采集 · {formatTimestamp(data.started)}</span><Badge variant="muted">{data.state === 'running' ? '采集中' : data.state === 'interrupted' ? '已中断' : '本批结束'}</Badge></div>
    <dl className="grid grid-cols-3 gap-3 sm:grid-cols-6">{items.map(([label, value]) => <div key={label}><dt className="text-xs text-muted-foreground">{label}</dt><dd className="text-lg font-semibold tabular-nums">{value}</dd></div>)}</dl>
    {data.reason && <p className="text-sm">{data.reason}</p>}
    <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">统计口径与检索进度</summary>
      <p className="mt-2">成功包含新资料与正文重复；重试 {data.retried} 次。失败和重试均消耗读取额度，今日已用 {data.used ?? '待更新'} / {data.limit}。每个链接当天最多尝试三次，额度或重试次数不足计入未尝试。</p>
      <p>检索/订阅异常 {data.search_errors} 次；尚可扩展的查询 {data.searches_remaining ?? 0} 个。分轮扩大搜索结果数量，不保证全平台覆盖。仅已取得的有效正文进入后续整理。</p>
      <CopyButton label="复制采集批次统计" text={() => JSON.stringify(data, null, 2)}>复制采集批次统计</CopyButton>
    </details>
  </section>
}
