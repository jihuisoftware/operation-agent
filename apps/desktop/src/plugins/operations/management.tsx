import type { PluginContext } from '@hermes/plugin-sdk'
import { useState } from 'react'

import { ActionEvidence, PublicationStatus } from './action-evidence'
import { ActionInspector } from './action-inspector'
import type { RecordRow } from './types'

interface ManagementProps {
  ctx: PluginContext
  refresh: () => Promise<unknown>
  onError: (error: string) => void
}

const states: Record<string, string> = {
  queued: '等待执行',
  executing: '执行中',
  published: '已发布',
  confirmed: '已核对成功',
  submitted: '已提交，待核对',
  unknown: '结果不明',
  blocked: '已阻止',
  failed: '失败',
  cancelled: '已取消',
  confirmed_not_published: '人工确认未成功'
}

export function ActionManager({ rows, ...props }: ManagementProps & { rows: RecordRow[] }) {
  return (
    <div className="grid gap-3">
      {rows.map(row => (
        <ActionCard {...props} key={row.id} row={row} />
      ))}
    </div>
  )
}

function ActionCard({ ctx, row, refresh, onError }: ManagementProps & { row: RecordRow }) {
  const [evidence, setEvidence] = useState('')
  const [resolution, setResolution] = useState('confirmed_not_published')
  const [pending, setPending] = useState(false)
  const state = String(row.state)

  const execute = async (operation: string) => {
    setPending(true)

    try {
      await ctx.rest(`/actions/${row.id}/${operation}`, { method: 'POST', body: { state: resolution, evidence } })
      await refresh()
    } catch (error) {
      onError(String(error))
    } finally {
      setPending(false)
    }
  }

  return (
    <article className="grid gap-2 rounded border p-3">
      <strong>
        {String(row.kind)} · {states[state] || state}
      </strong>
      <p className="break-all text-xs">
        动作 {row.id} · 规则 v{String(row.version)} · {String(row.day)}
      </p>
      {row.kind === 'publish' && <PublicationStatus result={typeof row.result === 'string' ? JSON.parse(row.result) : row.result} />}
      <pre className="whitespace-pre-wrap text-xs">{String(row.result)}</pre>
      <ActionInspector ctx={ctx} refresh={refresh} row={row} />
      <ActionEvidence ctx={ctx} row={row} />
      {['unknown', 'blocked', 'submitted', 'failed'].includes(state) && (
        <>
          <p>查看网页并核实实际结果，再填写证据。结果不明时不要重复执行。</p>
          <select
            aria-label="人工核对结果"
            className="border bg-background"
            onChange={e => setResolution(e.target.value)}
            value={resolution}
          >
            <option value="confirmed_not_published">确认未执行成功</option>
            <option value={row.kind === 'publish' ? 'published' : 'confirmed'}>确认已成功</option>
            <option value="failed">确认失败，暂不重试</option>
          </select>
          <input
            aria-label="核对证据"
            className="border bg-transparent p-2"
            onChange={e => setEvidence(e.target.value)}
            placeholder="结果链接或核对说明"
            value={evidence}
          />
          <button disabled={pending || !evidence.trim()} onClick={() => void execute('resolve')}>
            保存人工核对
          </button>
        </>
      )}
      {state === 'confirmed_not_published' && (
        <button disabled={pending} onClick={() => void execute('retry')}>
          按当前规则重新执行
        </button>
      )}
      {state === 'queued' && (
        <button disabled={pending} onClick={() => void execute('cancel')}>
          取消待执行动作
        </button>
      )}
    </article>
  )
}

export function ContentEditor({
  rows,
  assets,
  sources,
  ...props
}: ManagementProps & { rows: RecordRow[]; assets: RecordRow[]; sources: RecordRow[] }) {
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [assetIds, setAssetIds] = useState<string[]>([])
  const [sourceIds, setSourceIds] = useState<string[]>([])
  const [ready, setReady] = useState(false)

  const save = async () => {
    try {
      await props.ctx.rest('/records/content', {
        method: 'POST',
        body: { title, body, asset_ids: assetIds, source_ids: sourceIds, ready }
      })
      await props.refresh()
      props.onError('已保存新内容版本')
    } catch (error) {
      props.onError(String(error))
    }
  }

  const toggle = (values: string[], id: string) =>
    values.includes(id) ? values.filter(v => v !== id) : [...values, id]

  return (
    <section className="grid gap-3">
      <h2 className="text-lg">内容编辑与版本</h2>
      <select
        aria-label="加载内容版本"
        className="border bg-background"
        defaultValue=""
        onChange={e => {
          const row = rows.find(r => r.id === e.target.value)

          if (!row) {
            return
          }

          setTitle(String(row.title))
          setBody(String(row.body))
          setAssetIds(row.asset_ids as string[])
          setSourceIds(row.source_ids as string[])
          setReady(false)
        }}
      >
        <option value="">选择历史版本或创建新稿</option>
        {rows.map(r => (
          <option key={r.id} value={r.id}>
            {String(r.title)} · {String(r.day)}
          </option>
        ))}
      </select>
      <input
        aria-label="内容标题"
        className="border bg-transparent p-2"
        maxLength={20}
        onChange={e => setTitle(e.target.value)}
        placeholder="标题（20 字以内）"
        value={title}
      />
      <textarea
        aria-label="内容正文"
        className="border bg-transparent p-2"
        maxLength={900}
        onChange={e => setBody(e.target.value)}
        placeholder="正文、话题和来源说明"
        rows={8}
        value={body}
      />
      <p>选择获授权图片，第一张作为封面：</p>
      {assets
        .filter(a => !a.revoked)
        .map(a => (
          <label key={a.id}>
            <input
              checked={assetIds.includes(a.id)}
              onChange={() => setAssetIds(toggle(assetIds, a.id))}
              type="checkbox"
            />{' '}
            {String(a.name)}
          </label>
        ))}
      <p>引用资料：</p>
      {sources
        .filter(s => s.state === 'read')
        .map(s => (
          <label key={s.id}>
            <input
              checked={sourceIds.includes(s.id)}
              onChange={() => setSourceIds(toggle(sourceIds, s.id))}
              type="checkbox"
            />{' '}
            {String(s.title)}
          </label>
        ))}
      <label>
        <input checked={ready} onChange={e => setReady(e.target.checked)} type="checkbox" />{' '}
        纳入今日发布候选（仍需通过当前规则与自动检查）
      </label>
      <button onClick={() => void save()}>保存新版本</button>
      {rows.map(row => (
        <button
          className="text-left"
          key={row.id}
          onClick={() =>
            void props.ctx
              .rest<{ data: string }>(`/content/${row.id}/export`)
              .then(result => {
                const bytes = Uint8Array.from(atob(result.data), c => c.charCodeAt(0))
                const url = URL.createObjectURL(new Blob([bytes], { type: 'application/zip' }))
                const link = document.createElement('a')
                link.href = url
                link.download = `${String(row.title)}.zip`
                link.click()
                setTimeout(() => URL.revokeObjectURL(url), 1000)
              })
              .catch(error => props.onError(String(error)))
          }
        >
          导出内容包：{String(row.title)}
        </button>
      ))}
    </section>
  )
}
