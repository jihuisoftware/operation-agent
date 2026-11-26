import { Button, formatTimestamp, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'

import { ActionManager } from './management'
import type { RecordRow } from './types'
import { $workspaces, ownerKey } from './workspace-state'

const states: Record<string, string> = {
  attention: '待人工和人工处理中',
  auto: '待自动处理',
  manual: '待人工',
  working: '人工处理中',
  sending: '发送中',
  verify: '待核对',
  replied: '已回复',
  handled: '已处理',
  archived: '历史记录（只读）',
  transferred: '已转交'
}
interface Message {
  id: string
  kind: string
  account: string
  text: string
  reason: string
  reply: string
  state: string
  revision: string
  created: string
  action_id: string
  action?: RecordRow
  receipt?: Record<string, unknown>
  history?: { event: string; at: string; state?: string; text?: string; topic?: string; request?: { to?: string } }[]
}
interface Page {
  items: Message[]
  total: number
  next: number | null
}

export function MessagePage({ ctx }: { ctx: PluginContext }) {
  const [params, setParams] = useSearchParams()
  const source = params.get('source') || '',
    state = params.get('state') || '',
    selected = params.get('record') || ''
  const before = params.get('before') || '0'
  const [page, setPage] = useState<Page>()
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const refresh = () => setRevision(n => n + 1)
  const navigate = (key: string, value: string) =>
    setParams(previous => {
      const next = new URLSearchParams(previous)
      if (key !== 'record') next.delete('record')
      if (key !== 'before' && key !== 'record') next.delete('before')
      if (value) next.set(key, value)
      else next.delete(key)
      return next
    })
  useEffect(() => {
    let live = true
    setPage(undefined)
    setError('')
    void ctx.rest<Page>('/messages?' + new URLSearchParams({ source, state, before })).then(
      value => {
        if (live) setPage(value)
      },
      e => {
        if (live) setError(String(e))
      }
    )
    return () => {
      live = false
    }
  }, [ctx, source, state, before, revision])

  return (
    <section aria-label="消息处理" className="space-y-3 p-4">
      <header className="flex flex-wrap items-center gap-3">
        <h2 className="mr-auto font-semibold">消息处理 {page && `（${page.total}）`}</h2>
        <label>
          来源{' '}
          <select value={source} onChange={e => navigate('source', e.target.value)}>
            <option value="">全部</option>
            <option value="reply">收到的评论</option>
            <option value="dm">收到的私信</option>
          </select>
        </label>
        <label>
          状态{' '}
          <select value={state} onChange={e => navigate('state', e.target.value)}>
            <option value="">全部</option>
            {Object.entries(states).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <Button size="sm" variant="outline" onClick={refresh}>
          刷新
        </Button>
      </header>
      {error && <p role="alert">{error}</p>}
      {!page && !error && <p role="status">正在读取消息…</p>}
      {selected && (
        <MessageDetail
          key={selected}
          ctx={ctx}
          id={selected}
          revision={revision}
          saved={() => {
            navigate('record', '')
            refresh()
          }}
        />
      )}
      {page?.items.length === 0 && <p>当前没有符合条件的消息。</p>}
      {page?.items.map(row => (
        <button
          className="block w-full rounded border p-3 text-left"
          key={row.id}
          onClick={() => navigate('record', selected === row.id ? '' : row.id)}
        >
          <span className="text-sm font-medium">
            {({ dm: '私信', reply: '评论' } as Record<string, string>)[row.kind] || '历史消息'} · {states[row.state]}
          </span>
          <span className="ml-3 text-xs text-muted-foreground">{formatTimestamp(row.created)}</span>
          <p className="line-clamp-2">{row.text || '历史记录缺少原文'}</p>
        </button>
      ))}
      {page?.next && <Button onClick={() => navigate('before', String(page.next))}>更早消息</Button>}
      {before !== '0' && (
        <Button variant="ghost" onClick={() => navigate('before', '')}>
          返回最新
        </Button>
      )}
    </section>
  )
}

function MessageDetail({
  ctx,
  id,
  revision,
  saved
}: {
  ctx: PluginContext
  id: string
  revision: number
  saved: () => void
}) {
  const owner = useValue(host.state.requestOwner)
  const directory = useValue($workspaces)[ownerKey(owner)]
  const [row, setRow] = useState<Message>()
  const [target, setTarget] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const active = useRef(false)
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
    }
  }, [])
  useEffect(() => {
    let live = true
    setRow(undefined)
    setError('')
    void ctx.rest<Message>('/messages/' + encodeURIComponent(id)).then(
      r => {
        if (live) setRow(r)
      },
      e => {
        if (live) setError(String(e))
      }
    )
    return () => {
      live = false
    }
  }, [ctx, id, revision])
  const change = async (operation: string) => {
    if (!row || busy) return
    setBusy(true)
    try {
      await ctx.rest('/messages/' + encodeURIComponent(row.id), {
        method: 'POST',
        body: { operation, revision: row.revision, target_topic: target }
      })
      if (active.current) saved()
    } catch (e) {
      if (active.current) setError(String(e))
    } finally {
      if (active.current) setBusy(false)
    }
  }
  const business = directory?.catalog?.businesses.find(b => b.id === directory.selected?.business_id)
  const targets =
    directory?.catalog?.topics.filter(
      t =>
        !t.archived &&
        t.id !== directory.selected?.topic_id &&
        directory.catalog?.businesses.some(
          b => !b.archived && b.account === business?.account && b.id === t.business_id
        )
    ) || []
  return (
    <article className="space-y-2 rounded border p-4">
      {error && <p role="alert">{error}</p>}
      {row && (
        <>
          <h3 className="font-medium">
            {states[row.state]} · {row.account || '历史账号未知'}
          </h3>
          <p className="whitespace-pre-wrap">{row.text || '历史记录缺少原文'}</p>
          {row.reason && <p>处理原因 · {row.reason}</p>}
          {row.reply && (
            <p>
              {row.state === 'replied' ? '已回复' : '拟回复'} · {row.reply}
            </p>
          )}
          {row.action_id && (
            <details>
              <summary>平台回执</summary>
              <pre className="whitespace-pre-wrap">{JSON.stringify(row.receipt, null, 2)}</pre>
            </details>
          )}
          {row.state === 'verify' && row.action && (
            <ActionManager ctx={ctx} rows={[row.action]} refresh={async () => saved()} onError={setError} />
          )}
          {!!row.history?.length && (
            <details>
              <summary>处理记录</summary>
              {row.history.map((h, i) => (
                <p key={i}>
                  {formatTimestamp(h.at)} ·{' '}
                  {
                    (
                      { take: '人工接手', handle: '标记已处理', transfer: '转交主题', legacy: '旧记录' } as Record<
                        string,
                        string
                      >
                    )[h.event]
                  }{' '}
                  {h.state} {h.text} {h.request?.to}
                </p>
              ))}
            </details>
          )}
          {['auto', 'manual', 'working'].includes(row.state) && (
            <fieldset disabled={busy} className="flex flex-wrap gap-2">
              {row.state !== 'working' && <Button onClick={() => void change('take')}>人工接手</Button>}
              <Button variant="outline" onClick={() => void change('handle')}>
                标记已处理
              </Button>
              {!row.action_id && targets.length > 0 && (
                <>
                  <select aria-label="转交主题" value={target} onChange={e => setTarget(e.target.value)}>
                    <option value="">选择共用账号的主题</option>
                    {targets.map(t => (
                      <option key={t.id} value={t.id}>
                        {directory?.catalog?.businesses.find(b => b.id === t.business_id)?.name} / {t.name}
                      </option>
                    ))}
                  </select>
                  <Button disabled={!target} onClick={() => void change('transfer')}>
                    转交
                  </Button>
                </>
              )}
            </fieldset>
          )}
        </>
      )}
    </article>
  )
}
