import { Button, formatTimestamp, host, type PluginContext } from '@hermes/plugin-sdk'
import { useState } from 'react'

import { coverAssetIds, localInput, versionRequest } from './content-version-actions'
import type { RecordRow } from './types'
import { PublicationWaiting, type PublicationWait } from './publication-waiting'

interface Props {
  ctx: PluginContext
  row: RecordRow
  refresh: () => Promise<unknown>
}

export function ContentReview({ ctx, row, refresh }: Props) {
  const [time, setTime] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [newVersion, setNewVersion] = useState('')
  const [rescheduling, setRescheduling] = useState(false)
  const release = row.release as { state: string; publish_at: string; revision: number; detail?: string; waiting?: PublicationWait } | null

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

  const replace = async (file: File) => {
    setPending(true)
    setError('')

    try {
      const data = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result).split(',')[1])
        reader.onerror = () => reject(new Error('图片读取失败'))
        reader.readAsDataURL(file)
      })

      const asset = await ctx.rest<{ id: string }>('/assets', { method: 'POST', body: { name: file.name, data, authorized: true } })

      const result = await ctx.rest<{ id: string; original_schedule_retained: boolean }>(`/content/${row.id}/versions`, { method: 'POST', body: versionRequest(row, {
        asset_ids: coverAssetIds(row, asset.id)
      }) })

      await refresh()
      setNewVersion(result.id)
      setNotice('封面已更新到原内容，原审核与排期已失效；请重新审核后排期。')
    } catch (reason) { setError(String(reason)) } finally { setPending(false) }
  }

  if (row.publication_state) { return null }

  return <section aria-label="审核与排期" className="space-y-3">
    {release?.state === 'scheduled' && !rescheduling
      ? <><p>已审核，计划于 {formatTimestamp(release.publish_at)} 发布</p>
          <Button disabled={pending} onClick={() => { setTime(localInput(release.publish_at)); setRescheduling(true) }} variant="outline">调整发布时间</Button>
          <Button disabled={pending} onClick={() => void submit('cancel-schedule')} variant="outline">取消排期</Button></>
      : <><label className="grid gap-1">发布时间（本机时区）
          <input aria-label="发布时间" className="rounded border bg-background p-2" disabled={pending} onChange={event => setTime(event.target.value)} type="datetime-local" value={time} />
        </label>
          <Button disabled={pending || !time || !(row.asset_ids as string[] | undefined)?.length} onClick={() => void submit('approve')}>{rescheduling ? '确认改期' : '审核通过并定时发布'}</Button>
          {rescheduling && <Button disabled={pending} onClick={() => setRescheduling(false)} variant="ghost">放弃改期</Button>}
          <p className="text-xs text-muted-foreground">请核对全部图片与正文。此操作仅授权本篇稿件；到时需保持应用和账号在线。</p></>}
    <PublicationWaiting waiting={release?.waiting} />
    {release?.detail && <p>{release.detail}</p>}
    {release?.state === 'scheduled' && <p className="text-sm">保存封面修改会更新原内容并取消当前排期，请重新审核后设置发布时间。</p>}
    <label className="grid gap-1 text-sm">替换封面（上传即确认具有使用权，更新原内容并重新审核）
      <input accept="image/png,image/jpeg,image/webp" disabled={pending} onChange={event => {
        const file = event.target.files?.[0]

        if (file) { void replace(file) }
      }} type="file" />
    </label>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {newVersion && <Button onClick={() => host.navigate(`/content?tab=drafts&record=${encodeURIComponent(newVersion)}`)} variant="link">查看内容</Button>}
  </section>
}

export function GenerateContent({ ctx, refresh }: Pick<Props, 'ctx' | 'refresh'>) {
  const [pending, setPending] = useState(false)
  const [notice, setNotice] = useState('')

  const generate = async () => {
    setPending(true)
    setNotice('正在生成完整图文，完成后进入待审核')

    try {
      const { version } = await ctx.rest<{ version: number }>('/policy')

      const result = await ctx.rest<{ detail: string }>('/content/generate', { method: 'POST', timeoutMs: 1_800_000,
        body: { version, request_id: crypto.randomUUID() } })

      setNotice(result.detail)
      await refresh()
    } catch (reason) { setNotice(String(reason)) } finally { setPending(false) }
  }

  return <div className="space-y-2"><Button disabled={pending} onClick={() => void generate()}>生成待审图文</Button>
    <p className="text-sm text-muted-foreground">根据已有资料选题并生成正文；没有配图时自动制作文字封面，审核时可以替换。</p>
    {notice && <p role="status">{notice}</p>}</div>
}
