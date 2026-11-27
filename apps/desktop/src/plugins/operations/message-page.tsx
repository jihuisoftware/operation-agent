import { Button, formatTimestamp, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'

import { ActionManager } from './management'
import { PlatformAppIcon } from './platform-app-icon'
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
  followed: '已回关',
  ignored: '已忽略',
  handled: '已处理',
  archived: '历史记录（只读）',
  transferred: '本主题已转交'
}
const sources: Record<string, string> = { reply: '评论和 @', reaction: '赞和收藏', follow: '新增关注' }
const platforms = { xiaohongshu: '小红书', zhihu: '知乎' } as const
type Platform = keyof typeof platforms
const platformIds = Object.keys(platforms) as Platform[]

interface Message {
  platform?: Platform
  read_only?: boolean
  owner_topic?: string
  id: string
  kind: string
  target: string
  account: string
  text: string
  reason: string
  reply: string
  state: string
  revision: string
  platform_time?: string
  matching_terms?: string[]
  follow_disabled_reason?: string
  follows_me?: boolean
  already_following?: boolean
  action_id: string
  action?: RecordRow
  receipt?: Record<string, unknown>
  history?: { event: string; at: string; state?: string; text?: string; topic?: string; request?: { to?: string } }[]
}
interface Page {
  items: Message[]
  total: number
  next: string | null
}

export function MessagePage({ ctx }: { ctx: PluginContext }) {
  const [params, setParams] = useSearchParams()
  const platform = params.get('platform') || ''
  const source = params.get('source') || '',
    state = params.get('state') || '',
    selected = params.get('record') || ''
  const before = params.get('before') || '0'
  const [page, setPage] = useState<Page>()
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [syncing, setSyncing] = useState(false)
  const [pullPlatforms, setPullPlatforms] = useState<Platform[]>(['xiaohongshu'])
  const [notice, setNotice] = useState('')
  const refresh = () => setRevision(n => n + 1)
  const receive = async () => {
    setSyncing(true)
    setNotice('')
    try {
      const results: string[] = []
      for (const id of pullPlatforms) {
        try {
          const counts = await ctx.rest<Record<string, number>>('/messages/sync-notifications', {
            method: 'POST', body: { platform: id }, timeoutMs: 420000
          })
          results.push(platforms[id] + ' · ' + Object.entries(sources).map(([key, label]) => label + ' ' + counts[key] + ' 条').join(' · '))
        } catch (reason) {
          results.push(platforms[id] + '接收失败 · ' + String(reason))
        }
        setNotice(results.join('；'))
      }
    } finally {
      setSyncing(false)
      refresh()
    }
  }
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
    void ctx.rest<Page>('/messages?' + new URLSearchParams({ platform, source, state, before })).then(
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
  }, [ctx, platform, source, state, before, revision])

  return (
    <section aria-label="消息处理" className="space-y-3 p-4">
      <header className="flex flex-wrap items-center gap-3">
        <h2 className="mr-auto font-semibold">消息处理 {page && `（${page.total}）`}</h2>
        <label>
          平台{' '}
          <select value={platform} onChange={e => navigate('platform', e.target.value)}>
            <option value="">全部</option>
            {platformIds.map(id => <option key={id} value={id}>{platforms[id]}</option>)}
          </select>
        </label>
        <label>
          来源{' '}
          <select value={source} onChange={e => navigate('source', e.target.value)}>
            <option value="">全部</option>
            {Object.entries(sources).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            {source === 'dm' && <option value="dm">私信</option>}
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
        <Button disabled={syncing || !pullPlatforms.length} size="sm" onClick={() => void receive()}>{syncing ? '正在接收…' : '接收平台通知'}</Button>
        <details className="relative">
          <summary className="cursor-pointer rounded border px-3 py-1">拉取平台</summary>
          <fieldset aria-label="拉取平台" disabled={syncing} className="absolute right-0 z-10 min-w-max space-y-2 rounded border bg-background p-3 shadow">
            {platformIds.map(id => <label key={id} className="flex items-center gap-2">
              <input type="checkbox" checked={pullPlatforms.includes(id)} onChange={event => {
                const checked = event.target.checked
                setPullPlatforms(previous => checked ? [...previous, id] : previous.filter(value => value !== id))
              }} />
              {platforms[id]}
            </label>)}
          </fieldset>
        </details>
        <Button size="sm" variant="outline" onClick={refresh}>
          刷新
        </Button>
      </header>
      {notice && <p role="status">{notice}</p>}
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
          <span className="inline-flex items-center gap-1.5 align-middle text-sm font-medium">
            <PlatformAppIcon compact platform={row.platform || 'xiaohongshu'} />
            <span className="sr-only">{platforms[row.platform || 'xiaohongshu']}</span>
            {sources[row.kind] || (row.kind === 'dm' ? '私信' : '历史消息')} · {states[row.state]}
          </span>
          {row.platform_time && <span className="ml-3 text-xs text-muted-foreground">{row.platform_time}</span>}
          {row.read_only && <span className="ml-3 text-xs text-muted-foreground">由「{row.owner_topic}」处理</span>}
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
          <h3 className="flex items-center gap-1.5 font-medium">
            <PlatformAppIcon compact platform={row.platform || 'xiaohongshu'} />
            <span className="sr-only">{platforms[row.platform || 'xiaohongshu']}</span>
            {states[row.state]} · {row.account || '历史账号未知'}
          </h3>
          {row.platform_time && <p className="text-xs text-muted-foreground">{row.platform_time}</p>}
          <p className="whitespace-pre-wrap">{row.text || '历史记录缺少原文'}</p>
          {row.read_only && <p className="text-muted-foreground">此消息由「{row.owner_topic}」处理，可切换到该主题办理。</p>}
          <FollowerFacts row={row} />
          {row.reason && <p>处理原因 · {row.reason}</p>}
          {row.reply && (
            <p>
              {row.state === 'replied' ? '已回复' : '拟回复'} · {row.reply}
            </p>
          )}
          <MessageReceipt ctx={ctx} row={row} saved={saved} onError={setError} />
          {!!row.history?.length && (
            <details>
              <summary>处理记录</summary>
              {row.history.map((h, i) => (
                <p key={i}>
                  {formatTimestamp(h.at)} ·{' '}
                  {
                    (
                      { take: '人工接手', handle: '标记已处理', transfer: '转交主题', legacy: '旧记录', ignore: '忽略关注' } as Record<
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
          {!row.read_only && ['auto', 'manual', 'working'].includes(row.state) && (
            <fieldset disabled={busy} className="flex flex-wrap gap-2">
              <FollowActions row={row} change={change} />
              {row.state !== 'working' && <Button onClick={() => void change('take')}>人工接手</Button>}
              {(row.kind !== 'follow' || row.platform === 'zhihu') && <Button variant="outline" onClick={() => void change('handle')}>
                标记已处理
              </Button>}
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


interface ReceiptProps {
  ctx: PluginContext
  row: Message
  saved: () => void
  onError: (error: string) => void
}

function MessageReceipt({ ctx, row, saved, onError }: ReceiptProps) {
  if (row.read_only || !row.action_id) return null
  return <>
    <details>
      <summary>平台回执</summary>
      <pre className="whitespace-pre-wrap">{JSON.stringify(row.receipt, null, 2)}</pre>
    </details>
    {row.state === 'verify' && row.action && (
      <ActionManager ctx={ctx} rows={[row.action]} refresh={async () => saved()} onError={onError} />
    )}
  </>
}

function FollowerFacts({ row }: { row: Message }) {
  if (row.kind !== 'follow' || row.platform === 'zhihu') return null
  return <div className="text-sm">
    <p>平台用户 {row.target || '未知'}</p>
    <p>{row.state === 'followed' || row.already_following ? '已回关' : row.follows_me ? '对方已关注本账号' : '旧记录缺少关系证据'}</p>
    {!row.read_only && <p>匹配条件 · {row.matching_terms?.join('、') || '无匹配项'}</p>}
  </div>
}

function FollowActions({ row, change }: { row: Message; change: (operation: string) => Promise<void> }) {
  if (row.kind !== 'follow' || row.platform === 'zhihu') return null
  return <>
    <Button disabled={Boolean(row.follow_disabled_reason)} onClick={() => void change('follow')}>按规则回关</Button>
    <Button variant="outline" onClick={() => void change('ignore')}>忽略</Button>
    {row.follow_disabled_reason && <span className="text-sm">{row.follow_disabled_reason}</span>}
  </>
}
