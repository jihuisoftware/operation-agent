import { Button, host, type PluginContext } from '@hermes/plugin-sdk'
import { useCallback, useEffect, useState } from 'react'

import { AssetImage } from './asset-image'
import { ContentReview } from './content-review'
import { versionRequest } from './content-version-actions'
import { CoverStudio } from './cover-studio'
import { ImageStudio } from './image-studio'
import { ActionManager } from './management'
import type { RecordRow } from './types'
import { Records } from './workbench-widgets'
import { openWriter } from './writing/navigation'

interface Detail { content: RecordRow; sources: RecordRow[]; assets: RecordRow[]; action?: RecordRow }

export function ContentPreview({ ctx, identity, publication, refresh, snapshotKey }: { ctx: PluginContext; identity: string; publication: boolean; snapshotKey?: string; refresh: () => Promise<unknown> }) {
  const [data, setData] = useState<Detail | null>(null)
  const [error, setError] = useState('')
  const [evidence, setEvidence] = useState(false)
  const [coverOpen, setCoverOpen] = useState(false)
  const [visualOpen, setVisualOpen] = useState(false)
  const [newVersion, setNewVersion] = useState('')
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
      {data.content.id && <details onToggle={event => setCoverOpen(event.currentTarget.open)}><summary className="cursor-pointer">设计封面 · 三个候选与样式编辑</summary>
        {coverOpen && <CoverStudio ctx={ctx} refresh={changed} row={data.content} />}
      </details>}
      <details onToggle={event => setVisualOpen(event.currentTarget.open)}><summary className="cursor-pointer">杂志组图 · AI 主视觉与信息图</summary>
        {visualOpen && <ImageStudio apply={async job => {
          const result = await ctx.rest<{ id: string }>(`/visual-sets/${encodeURIComponent(job)}/apply`, { method: 'POST', body: versionRequest(data.content, {}) })
          setNewVersion(result.id); await changed()
        }} ctx={ctx} identity={data.content.id} kind="content" prepare={async () => ({ content_revision: data.content.content_revision })} />}
        {newVersion && <Button onClick={() => host.navigate(`/content?tab=drafts&record=${newVersion}`)} variant="link">查看新待审版本</Button>}
      </details>
      <ContentReview ctx={ctx} refresh={changed} row={data.content} />
      {data.action && <ActionManager ctx={ctx} onError={setError} refresh={changed} rows={[data.action]} />}
      {data.content.id && <Button onClick={() => openWriter(data.content.id)} variant="outline">编辑为新版本</Button>}
      {typeof data.content.parent_content_id === 'string' && <Button onClick={() => host.navigate(`/content?tab=drafts&record=${encodeURIComponent(String(data.content.parent_content_id))}`)} variant="link">查看上一版本</Button>}
      <details><summary className="cursor-pointer">引用来源</summary>{data.sources.filter(row => (data.content.source_ids as string[] || []).includes(row.id)).map(row => <p className="break-all text-sm" key={row.id}>{String(row.title || row.id)} · {String(row.url || '')}</p>)}</details>
      <details onToggle={event => setEvidence(event.currentTarget.open)}><summary className="cursor-pointer">完整依据与版本记录</summary>{evidence && <Records rows={[data.content]} />}</details>
    </>}
  </div>
}
