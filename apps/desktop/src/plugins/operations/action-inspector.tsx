import { Button, Codicon, formatTimestamp, host, LogView, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import type { RecordRow } from './types'

interface FinalSnapshot {
  id?: string
  account_id: string
  policy_version?: number
  created?: string
  content_hash?: string
  content: { title?: string; body?: string }
  assets: { id: string; name?: string; missing?: boolean }[]
  sources: { id: string; title?: string; url?: string }[]
}
interface Detail {
  issue: { kind: string; title: string; help: string }
  tracking: { state?: string; next_check_at?: string; attempts?: number }
  snapshot: FinalSnapshot
  manual_history: { id: string; state: string; evidence: string; actor: string; at: string; previous_result: unknown }[]
}
interface Props { ctx: PluginContext; row: RecordRow; refresh: () => Promise<unknown> }

export function ActionInspector(props: Props) {
  const owner = useValue(host.state.requestOwner)

  return <OwnedInspector {...props} key={`${owner.connectionId}:${owner.profile}:${props.row.id}`} owner={owner} />
}

function OwnedInspector({ ctx, row, refresh, owner }: Props & { owner: ReturnType<typeof host.state.requestOwner.get> }) {
  const [detail, setDetail] = useState<Detail | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [revision, setRevision] = useState(0)
  const result = typeof row.result === 'string' ? JSON.parse(row.result) : row.result || {}

  useEffect(() => {
    let active = true
    let loading = false

    const load = async () => {
      if (loading) { return }
      loading = true

      try {
        const next = await ctx.rest<Detail>(`/actions/${row.id}/detail`, { owner })

        if (active) { setDetail(next); setError('') }
      } catch (reason) { if (active) { setError(String(reason)) } }
      finally { loading = false }
    }

    void load()
    const timer = ['submitted', 'unknown', 'executing', 'queued'].includes(String(row.state)) ? setInterval(() => void load(), 5000) : undefined

    return () => { active = false; clearInterval(timer) }
  }, [ctx, owner, row.id, row.state, row.result, revision])

  const check = async () => {
    setBusy(true)

    try {
      await ctx.rest(`/actions/${row.id}/check`, { method: 'POST', owner })
      setRevision(value => value + 1)
      await refresh()
    } catch (reason) { setError(String(reason)) }
    finally { setBusy(false) }
  }

  const diagnostic = async () => {
    setBusy(true)

    try {
      const file = await ctx.rest<{ name: string; data: string }>(`/actions/${row.id}/diagnostic`, { owner })
      downloadDiagnostic(file)
    } catch (reason) { setError(String(reason)) }
    finally { setBusy(false) }
  }


  return <div className="space-y-3">
    {error && <p role="alert">{error}</p>}
    {detail && <>
      <div className="flex items-center gap-2"><Codicon name={detail.issue.kind === 'resolved' ? 'pass' : 'info'} /><strong>{detail.issue.title}</strong></div>
      <p className="text-sm text-muted-foreground">{detail.issue.help}</p>
      {detail.tracking.next_check_at && <p>{detail.tracking.state === 'checking' ? '正在只读核对' : detail.tracking.state === 'queued' ? '只读核对已排队' : `下次核对：${formatTimestamp(detail.tracking.next_check_at)}`} · 已核对 {detail.tracking.attempts || 0} 次</p>}
      <div className="flex flex-wrap gap-2">
        {['unknown', 'submitted'].includes(String(row.state)) && <Button disabled={busy || ['queued', 'checking'].includes(detail.tracking.state || '')} onClick={() => void check()}>立即核对（不重发）</Button>}
        {detail.issue.kind === 'login' && <Button onClick={() => host.navigate('/accounts')}>处理登录</Button>}
        <Button disabled={busy} onClick={() => void diagnostic()}>导出诊断包</Button>
      </div>
      {row.kind === 'publish' && <SnapshotView ctx={ctx} owner={owner} result={result} row={row} snapshot={detail.snapshot} />}
      {detail.manual_history.length > 0 && <details><summary>人工核对历史（{detail.manual_history.length}）</summary>{detail.manual_history.map(item => <div className="space-y-2 py-2" key={item.id}><p>{item.actor} · {formatTimestamp(item.at)} · {item.state}</p><p>{item.evidence}</p><details><summary>核对前原始回执</summary><LogView>{JSON.stringify(item.previous_result, null, 2)}</LogView></details></div>)}</details>}
    </>}
  </div>
}


function SnapshotView({ ctx, owner, row, snapshot, result }: { ctx: PluginContext; owner: ReturnType<typeof host.state.requestOwner.get>; row: RecordRow; snapshot: FinalSnapshot; result: Record<string, any> }) {
  const [showSnapshot, setShowSnapshot] = useState(false)
  const image = (assetId: string) => `/actions/${row.id}/snapshot/images/${assetId}`

  return <details onToggle={event => setShowSnapshot(event.currentTarget.open)}><summary className="cursor-pointer">最终稿与内容对比</summary>
        {showSnapshot && <div className="space-y-3 py-3">
          <p>账号：{snapshot.account_id} · 规则 v{snapshot.policy_version ?? '未知'}</p>
          {snapshot.created && <p>保存时间：{formatTimestamp(snapshot.created)}</p>}
          <h3 className="font-semibold">{snapshot.content.title}</h3>
          <p className="whitespace-pre-wrap">{snapshot.content.body}</p>
          <div className="grid grid-cols-2 gap-3">
            {snapshot.assets.map((asset, index) => <figure key={`${asset.id}:${index}`}><ProofImage ctx={ctx} owner={owner} path={image(asset.id)} /><figcaption>{index + 1}. {asset.name || '图片缺失'}{index === 0 && '（封面）'}</figcaption></figure>)}
          </div>
          {snapshot.sources.length > 0 && <details><summary>引用来源（{snapshot.sources.length}）</summary>{snapshot.sources.map(source => <p className="break-all" key={source.id}>{source.title || source.id} · {source.url}</p>)}</details>}
          {result.actual && <div><h3 className="font-semibold">平台实际内容</h3><p>{result.actual.title}</p><p className="whitespace-pre-wrap">{result.actual.body}</p></div>}
          {result.checks && <details><summary>逐项核对结果</summary><LogView>{JSON.stringify(result.checks, null, 2)}</LogView></details>}
          {result.checks?.images?.comparisons?.map((comparison: { asset_id: string; evidence_id?: string; similarity?: number; pixels_equal?: boolean; error?: string }, index: number) => <div className="space-y-2" key={index}>
            <p>图片 {index + 1} · 仅作人工参考：{comparison.similarity !== undefined ? `相似度 ${(comparison.similarity * 100).toFixed(1)}% · 解码像素${comparison.pixels_equal ? '相同' : '不同'}` : comparison.error}</p>
            <div className="grid grid-cols-2 gap-3"><figure><ProofImage ctx={ctx} owner={owner} path={image(comparison.asset_id)} /><figcaption>原图</figcaption></figure>{comparison.evidence_id && <figure><ProofImage ctx={ctx} owner={owner} path={`/browser-evidence/${encodeURIComponent(comparison.evidence_id)}`} /><figcaption>平台图参考缩略图</figcaption></figure>}</div>
          </div>)}
        </div>}
      </details>
}

function ProofImage({ ctx, owner, path }: { ctx: PluginContext; owner: ReturnType<typeof host.state.requestOwner.get>; path: string }) {
  const [src, setSrc] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    void ctx.rest<{ image?: string; data?: string; name?: string }>(path, { owner }).then(file => {
      if (active) { setSrc(file.image || `data:image/${file.name?.endsWith('.png') ? 'png' : file.name?.endsWith('.webp') ? 'webp' : 'jpeg'};base64,${file.data}`) }
    }).catch(reason => { if (active) { setError(String(reason)) } })

    return () => { active = false }
  }, [ctx, owner, path])

  return error ? <p role="alert">{error}</p> : src ? <img alt="内容核对图片" className="max-h-80 max-w-full object-contain" src={src} /> : <Codicon name="loading" spinning />
}

export function downloadDiagnostic(file: { name: string; data: string }) {
  const bytes = Uint8Array.from(atob(file.data), c => c.charCodeAt(0))
  const url = URL.createObjectURL(new Blob([bytes], { type: 'application/zip' }))
  const link = document.createElement('a')
  link.href = url
  link.download = file.name
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
