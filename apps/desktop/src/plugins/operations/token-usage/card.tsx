import { Button, Codicon, formatTimestamp, host, type PluginContext } from '@hermes/plugin-sdk'

import { number, queryString, timestamp, useUsage } from './data'
import type { Summary } from './types'
import { UsageTrend } from './visuals'

export function TokenUsageCard({ ctx, topic }: { ctx: PluginContext; topic?: string }) {
  const { data, error, retry } = useUsage<Summary>(ctx, '/usage/summary?' + queryString('day'))
  const summary = data && data.totals && data.groups && Array.isArray(data.trend) ? data : undefined

  return (
    <section aria-label="Token 用量摘要" className="space-y-3 rounded-lg bg-muted/30 p-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 font-semibold">
          <Codicon name="pulse" />
          Token 用量
        </h2>
        <Button onClick={() => host.navigate('/token-usage')} variant="ghost">
          查看详情
        </Button>
      </header>
      <p className="text-xs text-muted-foreground">当前 Profile 全部业务 · 今日</p>
      {error && (
        <p role="alert">
          用量更新失败，数据可能过期。
          <Button onClick={retry} variant="link">
            重试
          </Button>
        </p>
      )}
      {!summary && !error && <p role="status">正在读取用量…</p>}
      {summary && (
        <>
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
            <strong className="text-2xl tabular-nums">
              {number(summary.totals.total_tokens)} <span className="text-xs font-normal">已确认 Token</span>
            </strong>
            <span>输入 {number(summary.totals.prompt_tokens)}</span>
            <span>输出 {number(summary.totals.output_tokens)}</span>
          </div>
          <p className="text-xs text-muted-foreground">
            当前主题 {number((summary.groups.topic || []).find(item => item.id === topic)?.total_tokens || 0)} · 统计中{' '}
            {summary.totals.running || 0} 次 · 用量未知 {summary.totals.unknown || 0} 次
          </p>
          <UsageTrend compact data={summary} />
          <p className="text-xs text-muted-foreground">
            更新于 {formatTimestamp(timestamp(summary.until))}
            {summary.partial_history && ' · 仅包含开始记录后的数据'}
          </p>
        </>
      )}
    </section>
  )
}
