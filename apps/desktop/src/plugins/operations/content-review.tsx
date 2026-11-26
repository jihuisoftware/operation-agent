import { Button, formatTimestamp, type PluginContext } from '@hermes/plugin-sdk'
import { useState } from 'react'

import { localInput } from './content-version-actions'
import { type PublicationWait, PublicationWaiting } from './publication-waiting'
import { ContentReviewDecision } from './review-policy'
import type { RecordRow } from './types'

interface Props {
  ctx: PluginContext
  row: RecordRow
  refresh: () => Promise<unknown>
}

export function ContentReview({ ctx, row, refresh }: Props) {
  const visual = row.visual_check as { reason?: string; issues?: string[] } | undefined
  const [time, setTime] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [rescheduling, setRescheduling] = useState(false)
  const release = row.release as { reviewer?: string; state: string; publish_at: string; revision: number; detail?: string; waiting?: PublicationWait } | null

  const submit = async (operation: 'approve' | 'cancel-schedule') => {
    setPending(true)
    setError('')

    try {
      await ctx.rest(`/content/${row.id}/${operation}`, { method: 'POST', body: {
        expected_revision: release?.revision || 0,
        ...(operation === 'approve' ? { version: row.policy_version, content_revision: row.content_revision, publish_at: new Date(time).toISOString() } : {})
      } })
      await refresh()
      setRescheduling(false)
    } catch (reason) { setError(String(reason)) } finally { setPending(false) }
  }

  if (row.publication_state) { return null }

  return <section aria-label="审核与排期" className="space-y-3">
    {visual && <details><summary>查看图片评审详情</summary><p>{visual.reason}</p>
      {visual.issues?.map((issue, index) => <p key={index}>{String(issue)}</p>)}</details>}
    <ContentReviewDecision ctx={ctx} refresh={refresh} row={row} />
    {release?.state === 'scheduled' && !rescheduling
      ? <><p>{release?.reviewer === 'automatic' ? '自动审核通过' : '人工审核通过'}，计划于 {formatTimestamp(release.publish_at)} 发布</p>
          <Button disabled={pending} onClick={() => { setTime(localInput(release.publish_at)); setRescheduling(true) }} variant="outline">调整发布时间</Button>
          <Button disabled={pending} onClick={() => void submit('cancel-schedule')} variant="outline">取消排期</Button></>
      : <><label className="grid gap-1">发布时间（本机时区）
          <input aria-label="发布时间" className="rounded border bg-background p-2" disabled={pending} onChange={event => setTime(event.target.value)} type="datetime-local" value={time} />
        </label>
          <Button disabled={pending || !time || !(row.asset_ids as string[] | undefined)?.length} onClick={() => void submit('approve')}>{rescheduling ? '确认改期' : '审核通过并定时发布'}</Button>
          {rescheduling && <Button disabled={pending} onClick={() => setRescheduling(false)} variant="ghost">放弃改期</Button>}
          <p className="text-xs text-muted-foreground">请核对全部图片与正文。此操作仅授权本篇稿件；到时需保持应用和账号在线。</p></>}
    {row.visual_error && row.cover_origin === 'generated_typography' ? (
      <p className="text-sm">当前使用本地文字封面。杂志组图尚未完成：{String(row.visual_error)}</p>
    ) : null}
    <PublicationWaiting waiting={release?.waiting} />
    {release?.detail && <p>{release.detail}</p>}
    {release?.state === 'scheduled' && <p className="text-sm">保存封面修改会更新原内容并取消当前排期，请重新审核后设置发布时间。</p>}
    {error && <p role="alert">{error}</p>}
  </section>
}

export function GenerateContent({ ctx, refresh }: Pick<Props, 'ctx' | 'refresh'>) {
  const [pending, setPending] = useState(false)
  const [notice, setNotice] = useState('')

  const generate = async () => {
    setPending(true)
    setNotice('正在生成完整图文，完成后按当前审核策略处理')

    try {
      const { version } = await ctx.rest<{ version: number }>('/policy')

      const result = await ctx.rest<{ detail: string }>('/content/generate', { method: 'POST', timeoutMs: 1_800_000,
        body: { version, request_id: crypto.randomUUID() } })

      setNotice(result.detail)
      await refresh()
    } catch (reason) { setNotice(String(reason)) } finally { setPending(false) }
  }

  return <div className="space-y-2"><Button disabled={pending} onClick={() => void generate()}>生成图文</Button>
    <p className="text-sm text-muted-foreground">按主题设置生成正文与配图，完成后进入人工审核或自动排期。手写稿仍需人工审核。</p>
    {notice && <p role="status">{notice}</p>}</div>
}
