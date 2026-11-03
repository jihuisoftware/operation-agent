import { formatTimestamp } from '@hermes/plugin-sdk'

import { number } from './data'
import type { Summary, Totals } from './types'

const moduleLabels: Record<string, string> = {
  research: '信息采集',
  organize: '资料整理与归类',
  analytics: '数据分析',
  industry: '行业分析',
  topics: '选题策划',
  content: '图文内容生产',
  publish: '小红书图文发布',
  comments: '评论互动',
  dm: '收到私信处理',
  follow: '条件关注'
}

export const purposeLabel = (value: string) =>
  ({
    chat: 'AI 助手',
    vision: '图像理解',
    compression: '上下文压缩',
    title: '会话标题',
    web_extract: '网页提取',
    session_search: '会话检索'
  })[value] ||
  moduleLabels[value] ||
  value ||
  '辅助调用'

export function TokenMetrics({ totals }: { totals: Totals }) {
  return (
    <div className="grid grid-cols-2 gap-3 @3xl:grid-cols-3">
      {Object.entries({
        '已确认 Token': totals.total_tokens,
        '输入（含缓存）': totals.prompt_tokens,
        输出: totals.output_tokens,
        缓存读取: totals.cache_read_tokens,
        模型调用: totals.calls,
        用量缺失: totals.unknown || 0
      }).map(([label, value]) => (
        <div className="rounded bg-muted/30 p-3" key={label}>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="text-xl font-semibold tabular-nums">{number(value)}</p>
        </div>
      ))}
    </div>
  )
}

export function UsageTrend({ data, compact = false }: { data: Summary; compact?: boolean }) {
  const maximum = Math.max(1, ...data.trend.map(item => item.total_tokens))
  const width = 600
  const barWidth = width / Math.max(1, data.trend.length)
  const visibleBarWidth = Math.min(56, Math.max(2, barWidth - 4))

  return (
    <figure className="min-w-0 space-y-2">
      <figcaption className="text-xs text-muted-foreground">
        {compact ? '今日小时趋势' : '已确认 Token 趋势'} · {data.timezone}
      </figcaption>
      {!data.trend.length ? (
        <p className="text-xs text-muted-foreground">暂无已返回的调用记录</p>
      ) : (
        <svg
          aria-label="Token 用量趋势"
          className={`w-full text-primary ${compact ? 'h-12' : 'h-32'}`}
          preserveAspectRatio="none"
          role="img"
          viewBox={`0 0 ${width} 100`}
        >
          {data.trend.map((item, index) => {
            const height = (item.total_tokens / maximum) * 95
            const x = index * barWidth + (barWidth - visibleBarWidth) / 2

            return (
              <rect fill="currentColor" height={height} key={item.at} width={visibleBarWidth} x={x} y={100 - height}>
                <title>
                  {formatTimestamp(item.at)}：{number(item.total_tokens)} Token
                </title>
              </rect>
            )
          })}
        </svg>
      )}
      {!compact && data.trend.length > 0 && (
        <details>
          <summary className="cursor-pointer text-xs text-muted-foreground">查看趋势数据</summary>
          <div className="max-h-56 overflow-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>Token</th>
                </tr>
              </thead>
              <tbody>
                {data.trend.map(item => (
                  <tr key={item.at}>
                    <td>{formatTimestamp(item.at)}</td>
                    <td>{number(item.total_tokens)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </figure>
  )
}
