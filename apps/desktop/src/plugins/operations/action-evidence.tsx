import { Button, CopyButton, formatTimestamp, host, LogView, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import type { RecordRow } from './types'

interface StepRecord {
  event_id: number
  command_id: string
  sequence: number
  name: string
  phase: string
  at: string
  duration_ms?: number
  error?: string
  error_code?: string
  evidence_id?: string
  result?: unknown
}
const names: Record<string, string> = { execution: '网页任务', account: '核对账号', baseline: '记录发布前笔记', open_editor: '打开编辑页', upload: '上传并等待完成', fill: '填写并核对预览', submit: '提交发布', receipt: '读取平台回执', discover: '查找新笔记', verify_publication: '核对发布内容', inventory: '读取待处理列表', prepare_interaction: '准备互动', submit_interaction: '提交互动', verify_interaction: '核对互动结果' }
const phases: Record<string, string> = { started: '执行中', completed: '完成', failed: '异常' }
const execution: Record<string, string> = { not_submitted: '未提交', submitted: '已提交', verified: '已核对提交结果', unknown: '待核对' }
const platform: Record<string, string> = { reviewing: '审核中', published: '已发布', rejected: '审核未通过', unknown: '待确认' }
const content: Record<string, string> = { matched: '内容一致', mismatch: '内容不一致', incomplete: '核对不完整', unknown: '待核对' }

export function PublicationStatus({ result }: { result: Record<string, any> }) {
  const status = result.publication

  if (!status) { return <p className="text-sm text-muted-foreground">历史记录未分别记录平台审核与内容核对状态</p> }

  return <div aria-label="发布状态" className="flex flex-wrap gap-3 text-sm">
    {result.manual_verification && <span>人工已核对：{result.manual_verification.evidence}（以下保留自动核对结果）</span>}
    <span>执行：{execution[status.execution] || '待核对'}</span>
    <span>平台：{platform[status.platform] || '待确认'}</span>
    <span>内容：{content[status.content] || '待核对'}</span>
  </div>
}

export function ActionEvidence({ ctx, row }: { ctx: PluginContext; row: RecordRow }) {
  const owner = useValue(host.state.requestOwner)

  return <EvidenceDetails ctx={ctx} key={`${owner.connectionId}:${owner.profile}:${row.id}`} owner={owner} row={row} />
}

function EvidenceDetails({ ctx, row, owner }: { ctx: PluginContext; row: RecordRow; owner: ReturnType<typeof host.state.requestOwner.get> }) {
  const [open, setOpen] = useState(false)
  const [steps, setSteps] = useState<StepRecord[]>([])
  const [error, setError] = useState('')
  const [images, setImages] = useState<Record<string, string>>({})
  const running = ['queued', 'executing'].includes(String(row.state))

  useEffect(() => {
    if (!open) { return }
    let active = true
    let loading = false

    const refresh = async () => {
      if (loading) { return }
      loading = true

      try {
        const response = await ctx.rest<{ steps: StepRecord[] }>(`/actions/${row.id}/steps`, { owner })

        if (active) { setSteps(response.steps); setError('') }
      } catch (reason) { if (active) { setError(String(reason)) } }
      finally { loading = false }
    }

    void refresh()
    const timer = running ? setInterval(() => void refresh(), 3000) : undefined

    return () => { active = false; clearInterval(timer) }
  }, [ctx, owner, row.id, running, open])

  const errors = steps.filter(step => step.phase === 'failed')
  const latest = new Map<string, StepRecord>()

  for (const step of steps) { latest.set(`${step.command_id}:${step.sequence}`, step) }

  const loadImage = async (id: string) => {
    try {
      const response = await ctx.rest<{ image: string }>(`/browser-evidence/${encodeURIComponent(id)}`, { owner })
      setImages(previous => ({ ...previous, [id]: response.image }))
    } catch (reason) { setError(String(reason)) }
  }

  return <details onToggle={event => setOpen(event.currentTarget.open)} open={open}>
    <summary className="cursor-pointer">网页执行步骤与证据</summary>
    {open && <div className="space-y-3 py-3">
      <div className="flex gap-3">
        <CopyButton label="复制完整网页过程" text={() => JSON.stringify({ action: row, steps }, null, 2)}>复制完整过程</CopyButton>
        <CopyButton label="仅复制网页错误" text={() => JSON.stringify({ action_id: row.id, errors }, null, 2)}>仅复制错误</CopyButton>
      </div>
      {error && <p role="alert">{error}</p>}
      {!steps.length && <p className="text-sm text-muted-foreground">暂无网页步骤记录。</p>}
      {[...latest.values()].map(step => <details key={step.event_id}>
        <summary className="cursor-pointer">{names[step.name] || step.name} · {phases[step.phase]} · {formatTimestamp(step.at)}{step.duration_ms !== undefined && ` · ${(step.duration_ms / 1000).toFixed(1)} 秒`}</summary>
        <CopyButton label={`复制步骤 ${step.event_id}`} text={() => JSON.stringify(step, null, 2)}>复制这条记录</CopyButton>
        <LogView className="max-h-64">{JSON.stringify(step, null, 2)}</LogView>
        {step.evidence_id && <Button onClick={() => void loadImage(step.evidence_id!)}>查看现场截图</Button>}
        {step.evidence_id && images[step.evidence_id] && <img alt="网页步骤现场截图" className="max-w-full" src={images[step.evidence_id]} />}
      </details>)}
    </div>}
  </details>
}
