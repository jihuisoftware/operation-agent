import { Button, formatTimestamp, host, type PluginContext } from '@hermes/plugin-sdk'
import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'

import { moduleLabels } from './blueprint-types'
import { ActionManager } from './management'
import type { RecordRow } from './types'

type AttentionKind = 'unverified' | 'failed_today'
interface Page { items: RecordRow[]; total: number; next: number | null; day: string }
const titles = { unverified: '结果待核对', failed_today: '失败任务' }
const labels: Record<string, string> = { publish: '图文发布', comment: '主动评论', reply: '评论回复', dm: '收到私信', follow: '回关' }

export function AttentionPage({ ctx, kind }: { ctx: PluginContext; kind: AttentionKind }) {
  const [params] = useSearchParams()
  const day = kind === 'failed_today' ? params.get('day') || '' : ''

  const record = kind === 'unverified' ? params.get('record') || '' : ''
  return <Items ctx={ctx} day={day} key={kind + day + record} kind={kind} record={record} />
}

function Items({ ctx, kind, day, record }: { ctx: PluginContext; kind: AttentionKind; day: string; record: string }) {
  const [page, setPage] = useState<Page | null>(null)
  const [cursor, setCursor] = useState(0)
  const [revision, setRevision] = useState(0)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState(record)
  const refresh = useCallback(async () => { setRevision(n => n + 1) }, [])
  useEffect(() => {
    let active = true
    setError('')
    void ctx.rest<Page>(`/attention/${kind}?` + new URLSearchParams({ before: String(cursor), day, ...(record ? {record} : {}) }))
      .then(result => { if (active) { setPage(result) } })
      .catch(reason => { if (active) { setError(String(reason)) } })

    return () => { active = false }
  }, [ctx, cursor, day, kind, record, revision])

  const move = (next: number) => { setPage(null); setExpanded(''); setCursor(next) }

  return <section aria-label={titles[kind]} className="space-y-3 p-4">
    <header className="flex items-center gap-2">
      <h2 className="mr-auto font-semibold">{kind === 'failed_today' && (day || page?.day)} {titles[kind]} {page && `（${page.total}）`}</h2>
      <Button onClick={refresh} size="sm" variant="ghost">刷新</Button>
    </header>
    {error && <p role="alert">{error}</p>}
    {!page && !error && <p role="status">正在加载…</p>}
    {page?.items.length === 0 && <p>当前没有符合条件的记录。</p>}
    {page?.items.map(row => {
      if (kind === 'failed_today') {
        return <article className="space-y-1 rounded border p-3" key={row.id}>
          <strong>{moduleLabels[String(row.stage)] || String(row.stage)}</strong> · {formatTimestamp(String(row.started))}
          <p className="whitespace-pre-wrap">{String(row.detail || '未记录失败原因')}</p>
        </article>
      }

      return <article className="space-y-2 rounded border p-3" key={row.id}>
        <p>{labels[String(row.kind)] || String(row.kind)} · {String(row.target_name || row.id)} · {row.state === 'submitted' ? '已提交' : '结果未知'}</p>
        <p className="text-sm">{row.submitted_at ? '提交步骤完成' : '动作创建'} · {formatTimestamp(String(row.submitted_at || row.created))}</p>
        {Boolean(row.evidence) && <p className="text-sm">{String(row.evidence)}</p>}
        <Button aria-expanded={expanded === row.id} onClick={() => setExpanded(expanded === row.id ? '' : row.id)} variant="outline">查看回执与核对</Button>
        {Boolean(row.origin) && <Button variant="link" onClick={() => {
          const params = new URLSearchParams(row.origin as Record<string,string>)
          host.navigate((params.get('tab') === 'published' ? '/content?' : '/interactions?') + params)
        }}>查看原记录</Button>}
        {!row.origin && <pre className="whitespace-pre-wrap text-xs">{String(row.result || '暂无回执')}</pre>}
        {expanded === row.id && <ActionManager ctx={ctx} onError={setError} refresh={refresh} rows={[row]} />}
      </article>
    })}
    {page?.next && <Button onClick={() => move(page.next!)} variant="outline">更早记录</Button>}
    {cursor > 0 && <Button onClick={() => move(0)} variant="ghost">返回最新</Button>}
  </section>
}
