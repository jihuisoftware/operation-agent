import { Button, host, type PluginContext } from '@hermes/plugin-sdk'
import { useCallback, useEffect, useState } from 'react'

import { AssetImage } from './asset-image'
import { ContentReview } from './content-review'
import { ActionManager, ContentEditor } from './management'
import type { RecordRow } from './types'
import { Records } from './workbench-widgets'

interface Detail { content: RecordRow; sources: RecordRow[]; assets: RecordRow[]; action?: RecordRow }

export function ManualContent({ ctx, refresh }: { ctx: PluginContext; refresh: () => Promise<unknown> }) {
  const [data, setData] = useState<Pick<Detail, 'sources' | 'assets'> | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let disposed = false
    void ctx.rest<Pick<Detail, 'sources' | 'assets'>>('/content/editor-options').then(value => {
      if (!disposed) { setData(value) }
    }).catch(reason => { if (!disposed) { setError(String(reason)) } })

    return () => { disposed = true }
  }, [ctx])

  return <div className="space-y-3 rounded border p-4">
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p>正在读取可用素材和来源…</p>}
    {data && <ContentEditor assets={data.assets} ctx={ctx} onError={setError} refresh={refresh} rows={[]} sources={data.sources} />}
  </div>
}

export function ContentPreview({ ctx, identity, publication, refresh, snapshotKey }: { ctx: PluginContext; identity: string; publication: boolean; snapshotKey?: string; refresh: () => Promise<unknown> }) {
  const [data, setData] = useState<Detail | null>(null)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(false)
  const [evidence, setEvidence] = useState(false)
  const [revision, setRevision] = useState(0)
  const changed = useCallback(async () => { setRevision(value => value + 1); await refresh() }, [refresh])
  useEffect(() => {
    let disposed = false
    void ctx.rest<Detail>(publication ? `/content/publications/${encodeURIComponent(identity)}` : `/content/${encodeURIComponent(identity)}/details`)
      .then(value => { if (!disposed) { setData(value); setError('') } })
      .catch(reason => { if (!disposed) { setError(String(reason)) } })

    return () => { disposed = true }
  }, [ctx, identity, publication, revision, snapshotKey])

  return <div className="space-y-4">
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p>正在读取完整稿件…</p>}
    {data && <>
      <h3 className="font-semibold">{String(data.content.title || '发布稿件')}</h3>
      <p className="text-sm">目标账号：{String(data.content.target_account || '请先确认发布账号')} · 依据日期：{String(data.content.day || '未记录')}</p>
      <div className="grid gap-3 sm:grid-cols-2">{((data.content.asset_ids || []) as string[]).map(id => <AssetImage ctx={ctx} id={id} key={id} />)}</div>
      <p className="whitespace-pre-wrap break-words">{String(data.content.body || '')}</p>
      <ContentReview ctx={ctx} refresh={changed} row={data.content} />
      {data.action && <ActionManager ctx={ctx} onError={setError} refresh={changed} rows={[data.action]} />}
      {data.content.id && <details onToggle={event => setEditing(event.currentTarget.open)}><summary className="cursor-pointer">编辑为新版本</summary>
        {editing && <ContentEditor assets={data.assets} ctx={ctx} onError={setError} refresh={changed} rows={[data.content]} sources={data.sources} />}
      </details>}
      {typeof data.content.parent_content_id === 'string' && <Button onClick={() => host.navigate(`/content?tab=drafts&record=${encodeURIComponent(String(data.content.parent_content_id))}`)} variant="link">查看上一版本</Button>}
      <details><summary className="cursor-pointer">引用来源</summary>{data.sources.filter(row => (data.content.source_ids as string[] || []).includes(row.id)).map(row => <p className="break-all text-sm" key={row.id}>{String(row.title || row.id)} · {String(row.url || '')}</p>)}</details>
      <details onToggle={event => setEvidence(event.currentTarget.open)}><summary className="cursor-pointer">完整依据与版本记录</summary>{evidence && <Records rows={[data.content]} />}</details>
    </>}
  </div>
}
