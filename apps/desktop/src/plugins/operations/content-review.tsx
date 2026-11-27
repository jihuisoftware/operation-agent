import { Button, formatTimestamp, type PluginContext } from '@hermes/plugin-sdk'
import { useState } from 'react'

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
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const release = row.release as { reviewer?: string; state: string; publish_at: string; revision: number; detail?: string; waiting?: PublicationWait } | null

  const submit = async (operation: 'approve' | 'cancel-schedule') => {
    setPending(true)
    setError('')

    try {
      await ctx.rest(`/content/${row.id}/${operation}`, { method: 'POST', body: {
        expected_revision: release?.revision || 0,
        ...(operation === 'approve' ? { version: row.policy_version, content_revision: row.content_revision } : {})
      } })
      await refresh()
    } catch (reason) { setError(String(reason)) } finally { setPending(false) }
  }

  if (row.publication_state) { return null }

  return <section aria-label="审核与排期" className="space-y-3">
    {visual && <details><summary>查看图片评审详情</summary><p>{visual.reason}</p>
      {visual.issues?.map((issue, index) => <p key={index}>{String(issue)}</p>)}</details>}
    <ContentReviewDecision ctx={ctx} refresh={refresh} row={row} />
    {release && ['scheduled','waiting_slot'].includes(release.state)
      ? <><p>{release.reviewer === 'automatic' ? '自动审核通过' : '人工审核通过'} · {release.publish_at ? formatTimestamp(release.publish_at) : '等待账号自动排期'}</p>
          <Button disabled={pending} onClick={() => void submit('cancel-schedule')} variant="outline">取消排期</Button></>
      : <Button disabled={pending || !(row.asset_ids as string[] | undefined)?.length} onClick={() => void submit('approve')}>审核通过</Button>}
    {row.visual_error && row.cover_origin === 'generated_typography' ? (
      <p className="text-sm">当前使用本地文字封面。杂志组图尚未完成：{String(row.visual_error)}</p>
    ) : null}
    <PublicationWaiting waiting={release?.waiting} />
    {release?.detail && <p>{release.detail}</p>}
    {release?.state === 'scheduled' && <p className="text-sm">保存封面修改会更新原内容并取消当前排期，重新审核后由账号自动排期。</p>}
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
