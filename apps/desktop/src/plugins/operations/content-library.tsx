import { Button, formatTimestamp, type PluginContext } from '@hermes/plugin-sdk'
import { useCallback, useEffect, useState } from 'react'

import { AssetImage } from './asset-image'
import { ContentPreview, ManualContent } from './content-preview'
import { GenerateContent } from './content-review'
import type { RecordRow } from './types'

interface Summary extends RecordRow {
  title?: string
  excerpt?: string
  created: string
  asset_ids: string[]
  publication_state?: string
  quality_pass?: boolean | number
  quality_reason?: string
  release?: { state: string; publish_at?: string; account_id?: string; detail?: string }
}
interface Catalog {
  compact: boolean
  content?: Summary[]
  actions: Summary[]
  next?: string
  has_active: boolean
  counts: { drafts: number; pending: number; published: number }
}

const states: Record<string, string> = { queued: '等待发布', executing: '正在发布', submitted: '已提交待核对', unknown: '结果待核对',
  published: '已发布', confirmed: '已核对成功', failed: '发布失败', cancelled: '已取消', blocked: '需要处理', confirmed_not_published: '已确认未发布' }

const filters = [['all', '全部'], ['in_progress', '进行中'], ['needs_attention', '待核对 / 待处理'], ['published', '已发布'], ['failed', '失败 / 取消']]
const emptyMessages: Record<string, string> = { pending: '暂无已排期稿件，审核通过后会显示在这里。', published: '当前筛选下暂无发布记录。', drafts: '暂无待审核稿件，可以生成图文或选择其他分类。' }

function label(row: Summary) {
  const status = row.publication as { platform?: string } | null

  if (['submitted', 'unknown'].includes(row.publication_state || '') && status?.platform === 'published') {
    return row.verification_stale ? '此前确认发布 · 待复核' : '平台已发布 · 内容待核对'
  }

  if (row.publication_state) { return states[row.publication_state] || row.publication_state }

  if (row.release?.state === 'scheduled') { return '已排期' }

  if (['paused', 'needs_attention'].includes(row.release?.state || '')) { return '排期待处理' }

  return '待审核'
}

function actionLabel(row: Summary, tab: string) {
  if (row.publication_state) { return '查看发布结果' }

  return tab === 'pending' ? '查看或调整排期' : '预览与审核'
}

function ContentToolbar({ counts, restricted, refresh, showAll }: { counts?: Catalog['counts']; restricted: boolean; refresh: () => Promise<unknown>; showAll: () => void }) {
  return <div className="flex flex-wrap items-center gap-3 text-sm">
    {counts && <p className="mr-auto text-muted-foreground">待审核 {counts.drafts} · 已排期 {counts.pending} · 发布记录 {counts.published}</p>}
    {restricted && <Button onClick={showAll} variant="outline">查看全部记录</Button>}
    <Button onClick={() => void refresh()} variant="outline">刷新内容</Button>
  </div>
}

function emptyMessage(tab: string, record: string) {
  return record ? '未找到指定记录，可返回全部内容。' : emptyMessages[tab]
}

export function ContentLibrary({ ctx, tab, record = '' }: { ctx: PluginContext; tab: string; record?: string }) {
  const [data, setData] = useState<Catalog | null>(null)
  const [error, setError] = useState('')
  const [cursor, setCursor] = useState('')
  const [status, setStatus] = useState('all')
  const [recordFilter, setRecordFilter] = useState(record)
  const [selected, setSelected] = useState<string | null>(record || null)
  const [revision, setRevision] = useState(0)
  const [writing, setWriting] = useState(false)
  const refresh = useCallback(async () => { setRevision(value => value + 1) }, [])
  const polling = data?.has_active ? 5000 : tab === 'pending' ? 30000 : 0
  useEffect(() => {
    let disposed = false, busy = false

    const load = async () => {
      if (busy) { return }
      busy = true

      try {
        const query = new URLSearchParams({ filter: tab, before: cursor || '0', record: recordFilter, status, compact: 'true' })
        const value = await ctx.rest<Catalog>(`/library/content?${query}`)

        if (!value.compact) { throw new Error('请重启后台以加载新的内容管理接口') }

        if (!disposed) { setData(value); setError('') }
      } catch (reason) { if (!disposed) { setError(String(reason)) } }
      finally { busy = false }
    }

    const visible = () => { if (!document.hidden) { void load() } }
    void load()
    const timer = polling ? setInterval(visible, polling) : undefined
    document.addEventListener('visibilitychange', visible)
    window.addEventListener('focus', visible)

    return () => { disposed = true; clearInterval(timer); document.removeEventListener('visibilitychange', visible); window.removeEventListener('focus', visible) }
  }, [ctx, tab, cursor, recordFilter, status, revision, polling])
  const rows = tab === 'published' ? data?.actions || [] : data?.content || []

  const showAll = () => { setRecordFilter(''); setCursor(''); setSelected(null); setData(null); setRevision(value => value + 1) }

  return <div className="space-y-4 p-4">
    <ContentToolbar counts={data?.counts} refresh={refresh} restricted={Boolean(recordFilter)} showAll={showAll} />
    {tab === 'drafts' && <GenerateContent ctx={ctx} refresh={refresh} />}
    {tab === 'drafts' && <Button aria-expanded={writing} onClick={() => setWriting(value => !value)} variant="outline">{writing ? '收起写稿' : '手动写稿'}</Button>}
    {writing && <ManualContent ctx={ctx} refresh={refresh} />}
    {tab === 'published' && <div aria-label="发布状态筛选" className="flex flex-wrap gap-2">{filters.map(([value, title]) => <Button aria-pressed={status === value} key={value} onClick={() => {
      setStatus(value); showAll()
    }} size="sm" variant={status === value ? 'secondary' : 'ghost'}>{title}</Button>)}</div>}
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p role="status">正在加载内容…</p>}
    {data && !rows.length && <p className="rounded border border-dashed p-8 text-center text-muted-foreground">{emptyMessage(tab, recordFilter)}</p>}
    {rows.map(row => <article className="overflow-hidden rounded-xl border" key={row.id}>
      <div className="flex gap-4 p-4">
        {row.asset_ids?.[0] && <div className="w-24 shrink-0"><AssetImage ctx={ctx} id={row.asset_ids[0]} /></div>}
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">{row.title || '未命名图文'}</h2><span className="rounded bg-muted px-2 py-1 text-xs">{label(row)}</span></div>
          <p className="line-clamp-3 whitespace-pre-wrap text-sm text-muted-foreground">{row.excerpt}</p>
          <p className="text-xs text-muted-foreground">{formatTimestamp(row.created)}{row.release?.publish_at && ` · 发布时间：${formatTimestamp(row.release.publish_at)}`}</p>
          {Boolean(row.parent_content_id) && <p className="text-xs text-muted-foreground">{row.manual_revision ? '人工编辑版本' : '自动修订版本'} · 原稿已保留</p>}
          {row.release?.account_id && <p className="text-xs">发布账号：{row.release.account_id}</p>}
          {(row.quality_pass === false || row.quality_pass === 0) && <p className="text-sm">自动检查待完善：{row.quality_reason}</p>}
          {row.release?.detail && <p className="text-sm">{row.release.detail}</p>}
          <Button aria-expanded={selected === row.id} onClick={() => setSelected(selected === row.id ? null : row.id)} size="sm" variant="outline">
            {selected === row.id ? '收起详情' : actionLabel(row, tab)}
          </Button>
        </div>
      </div>
      {selected === row.id && <div className="border-t p-4"><ContentPreview ctx={ctx} identity={row.id} publication={tab === 'published'} refresh={refresh}
        snapshotKey={JSON.stringify([row.publication_state, row.publication, row.checked_at, row.release])} /></div>}
    </article>)}
    <div className="flex gap-2">
      {data?.next && <Button onClick={() => { setCursor(data.next!); setSelected(null); setData(null) }} variant="outline">更早记录</Button>}
      {cursor && <Button onClick={() => { setCursor(''); setSelected(null); setData(null) }} variant="ghost">返回最新</Button>}
    </div>
  </div>
}
