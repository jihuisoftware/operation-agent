import { Button, CopyButton, formatTimestamp, host, type PluginContext } from '@hermes/plugin-sdk'
import { useCallback, useEffect, useState } from 'react'

import { AssetImage } from './asset-image'
import { EvidenceStorage } from './evidence-storage'
import { ActionManager, ContentEditor } from './management'
import { PausedRuns } from './paused-runs'
import { ReportCard } from './report-card'
import type { RecordRow } from './types'
import { Assets, NewRecord, Records } from './workbench-widgets'
import { InboxTransfer } from './workspace-inbox'

export interface Library {
  task?: RecordRow[]
  asset?: RecordRow[]
  content?: RecordRow[]
  source?: RecordRow[]
  inbox?: RecordRow[]
  block?: RecordRow[]
  report?: RecordRow[]
  runs?: RecordRow[]
  actions: RecordRow[]
  next?: string
}

export function LibraryPage({
  ctx,
  section,
  filter = '',
  record = ''
}: {
  ctx: PluginContext
  section: string
  filter?: string
  record?: string
}) {
  const [data, setData] = useState<Library | null>(null)
  const [error, setError] = useState('')
  const [cursor, setCursor] = useState('')

  const refresh = useCallback(async () => {
    const value = await ctx.rest<Library>(
      `/library/${section}?before=${cursor || 0}&filter=${filter}&record=${encodeURIComponent(record)}`
    )

    setData(value)
  }, [ctx, section, cursor, filter, record])

  useEffect(() => {
    let disposed = false
    let busy = false

    const load = async () => {
      if (busy) {
        return
      }

      busy = true

      try {
        const value = await ctx.rest<Library>(
          `/library/${section}?before=${cursor || 0}&filter=${filter}&record=${encodeURIComponent(record)}`
        )

        if (!disposed) {
          setData(value)
          setError('')
        }
      } catch (reason) {
        if (!disposed) {
          setError(String(reason))
        }
      } finally {
        busy = false
      }
    }

    void load()
    const timer = setInterval(() => void load(), 5000)

    return () => {
      disposed = true
      clearInterval(timer)
    }
  }, [ctx, section, cursor, filter, record])
  const props = { ctx, refresh, onError: setError }

  return (
    <div className="space-y-4 p-4 text-sm">
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p role="status">正在加载…</p>}
      {data && (
        <>
          <LibraryContents {...props} data={data} filter={filter} section={section} />
          {data.next && (
            <Button onClick={() => setCursor(data.next!)} variant="outline">
              更早记录
            </Button>
          )}
          {cursor && (
            <Button onClick={() => setCursor('')} variant="ghost">
              返回最新
            </Button>
          )}
        </>
      )}
    </div>
  )
}

interface ContentProps {
  ctx: PluginContext
  data: Library
  section: string
  filter: string
  refresh: () => Promise<unknown>
  onError: (error: string) => void
}

function LibraryContents({ data, section, filter, ...props }: ContentProps) {
  const { ctx } = props
  const content = (data.content || []).filter(row => matchesContent(row, filter))

  const actions = data.actions

  return (
    <>
      {section === 'assets' && (
        <>
          <Assets {...props} content={[]} rows={data.asset || []} />
          <EvidenceStorage ctx={ctx} />
        </>
      )}
      {section === 'content' && filter !== 'published' && (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            {content.map(row => (
              <ContentCard ctx={ctx} key={row.id} row={row} />
            ))}
          </div>
          <details>
            <summary className="cursor-pointer">编辑内容版本</summary>
            <ContentEditor {...props} assets={data.asset || []} rows={content} sources={data.source || []} />
          </details>
        </>
      )}
      {section === 'content' &&
        filter === 'published' &&
        actions.map(row => <PublicationCard {...props} key={row.id} row={row} />)}
      {section === 'interactions' && (
        <>
          <ActionManager {...props} rows={actions} />
          <details>
            <summary className="cursor-pointer">待处理与上下文</summary>
            <InboxTransfers data={data} filter={filter} {...props} />
            <Records
              rows={[...(data.inbox || []).filter(row => !filter || row.kind === filter), ...(data.block || [])]}
            />
          </details>
        </>
      )}
      {section === 'history' && (
        <>
          <PausedRuns ctx={ctx} />
          <NewRecord ctx={ctx} kind="task" onError={props.onError} onSaved={props.refresh} />
          <Records rows={data.task || []} />
          <CopyButton label="复制执行记录" text={JSON.stringify(data.runs, null, 2)} />
          <Records rows={data.runs || []} />
        </>
      )}
      {section === 'reports' && (data.report || []).map(row => <ReportCard ctx={ctx} key={row.id} row={row} />)}
      {!actions.length && ['interactions', 'content'].includes(section) && (
        <p className="text-muted-foreground">暂无外部执行记录；未提交的内容不会标记为已发布。</p>
      )}
    </>
  )
}

function matchesContent(row: RecordRow, filter: string) {
  if (filter !== 'pending') { return !row.ready }

  return row.ready === true && !['published', 'confirmed', 'submitted', 'unknown', 'executing', 'queued'].includes(String(row.publication_state))
}

function InboxTransfers({ data, filter, ctx, refresh, onError }: Omit<ContentProps, 'section'>) {
  return (data.inbox || []).filter(row => !filter || row.kind === filter).map(row => <InboxTransfer ctx={ctx} failed={onError} key={row.id} row={row} saved={refresh} />)
}

function ContentCard({ ctx, row }: { ctx: PluginContext; row: RecordRow }) {
  const ids = (row.asset_ids || []) as string[]

  return (
    <article className="min-w-0 space-y-2 rounded-lg bg-muted/30 p-3">
      {ids.length > 0 && <AssetImage ctx={ctx} id={ids[0]} />}
      <h3 className="font-medium">{String(row.title)}</h3>
      <p className="text-xs text-muted-foreground">
        {row.publication_state
          ? (
              {
                published: '已发布',
                confirmed: '已核对成功',
                submitted: '已提交待核对',
                unknown: '结果待核对',
                failed: '发布失败',
                cancelled: '已取消'
              } as Record<string, string>
            )[String(row.publication_state)] || '正在处理'
          : row.ready
            ? '待发布'
            : '待完善草稿'}{' '}
        · {formatTimestamp(String(row.created))}
      </p>
      <details>
        <summary className="cursor-pointer">查看正文与来源</summary>
        <p className="whitespace-pre-wrap break-words">{String(row.body)}</p>
        <Records rows={[row]} />
      </details>
      {!ids.length && (
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => host.navigate('/materials?tab=assets')} variant="link">
            添加授权图片
          </Button>
          <CopyButton
            label="复制纯文字内容"
            text={`${String(row.title)}\n\n${String(row.body)}`}
          >
            复制纯文字内容（可粘贴到文字渠道）
          </CopyButton>
        </div>
      )}
    </article>
  )
}

function PublicationCard({ row, ...props }: Omit<ContentProps, 'data' | 'section' | 'filter'> & { row: RecordRow }) {
  const payload = typeof row.data === 'string' ? JSON.parse(row.data) : row.data
  const content = payload?.content

  return (
    <article className="space-y-3">
      {content && (
        <ContentCard
          ctx={props.ctx}
          row={{ ...content, id: String(content.id || row.id), created: row.created, publication_state: row.state }}
        />
      )}
      <ActionManager {...props} rows={[row]} />
    </article>
  )
}
