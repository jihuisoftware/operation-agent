import { Button, type PluginContext } from '@hermes/plugin-sdk'
import { useState } from 'react'

import { ActionEvidence, PublicationStatus } from './action-evidence'
import { ActionInspector } from './action-inspector'
import type { RecordRow } from './types'
import { openWriter } from './writing/navigation'

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

const kinds: Record<string, string> = { publish: '图文发布', comment: '主动评论', reply: '评论回复', dm: '私信处理', follow: '回关' }

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
        {kinds[String(row.kind)] || String(row.kind)} · {states[state] || state}
      </strong>
      <p className="break-all text-xs">
        动作 {row.id} · 规则 v{String(row.version)} · {String(row.day)}
      </p>
      {row.kind === 'publish' && <PublicationStatus result={typeof row.result === 'string' ? JSON.parse(row.result) : row.result} />}
      <details><summary className="cursor-pointer">原始执行回执</summary><pre className="whitespace-pre-wrap text-xs">{typeof row.result === 'string' ? row.result : JSON.stringify(row.result, null, 2)}</pre></details>
      <ActionInspector ctx={ctx} refresh={refresh} row={row} />
      <ActionEvidence ctx={ctx} row={row} />
      {(['unknown', 'blocked', 'submitted', 'failed'].includes(state) || (row.kind === 'publish' && ['cancelled', 'confirmed_not_published'].includes(state))) && (
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

export function ContentEditor({ rows }: ManagementProps & { rows: RecordRow[]; assets: RecordRow[]; sources: RecordRow[] }) {
  const [selected, setSelected] = useState(rows.length === 1 ? rows[0].id : '')

  return <section className="flex flex-wrap gap-2">
    <select aria-label="加载内容版本" className="border bg-background p-2" onChange={event => setSelected(event.target.value)} value={selected}>
      <option value="">全新手稿</option>{rows.map(row => <option key={row.id} value={row.id}>{String(row.title || row.id)}</option>)}
    </select>
    <Button onClick={() => openWriter(selected)}>打开独立写稿页</Button>
    <p className="text-sm text-muted-foreground">编辑现有稿件会建立工作副本，原稿和排期保持不变。</p>
  </section>
}
