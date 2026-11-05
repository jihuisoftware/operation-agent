import { Button, CopyButton, formatTimestamp, LogView, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import { ActionManager } from '../management'
import type { RecordRow } from '../types'

import { type Detail, hasError, type Run, states, type Step } from './records'
import { eventNames } from './task-guide'

export interface Artifact { id: string; kind: string; created: string; title?: string; state?: string; error?: string }
export interface ModelAttempt { id: string; model: string; provider: string; state: string; started: number; received?: number; total_tokens?: number | null; input_tokens?: number | null; output_tokens?: number | null; error_type: string }
export interface TaskDetail {
  run: Run; task: string; step: Step & { result?: unknown }; attempts: { id: string; state: string; started: string; ended?: string; detail: string }[]
  events: Detail['events']; more: boolean; cursor: number; artifacts: Artifact[]; actions: RecordRow[]; model_attempts: ModelAttempt[]
  notes: { id: string; created: string; text: string }[]; policy?: unknown; trace_notice: string
  original_step?: unknown
}
export type Api = <T>(path: string, body?: unknown) => Promise<T>
const json = (value: unknown) => JSON.stringify(value, null, 2)
const kinds: Record<string, string> = { source: '原始资料', organized_source: '整理结果', organization: '整理汇总', organization_part: '长文分段', organization_merge: '长文合并', analytics_report: '统计报告', industry_report: '行业分析', industry_batch: '分析批次', brief: '选题结果', content: '内容版本', content_revision_attempt: '自动修订尝试', check: '内容检查', report: '运营日报', model_trace: '模型业务输入与输出' }

function Screenshot({ identity, api }: { identity: string; api: Api }) {
  const [value, setValue] = useState('')
  const [error, setError] = useState('')

  const show = async () => {
    try { setValue((await api<{ image: string }>(`/browser-evidence/${encodeURIComponent(identity)}`)).image) }
    catch (reason) { setError(String(reason)) }
  }

  return <div>{value ? <img alt="本步骤保存的网页截图" className="max-h-96 max-w-full object-contain" src={value} />
    : <Button onClick={() => void show()} variant="outline">查看本步骤网页截图</Button>}{error && <p role="alert">{error}</p>}</div>
}

export function ArtifactView({ item, api, base }: { item: Artifact; api: Api; base: string }) {
  const [data, setData] = useState<unknown>()
  const [error, setError] = useState('')
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!open) { return }
    let active = true
    void api(`${base}/artifacts/${encodeURIComponent(item.id)}`).then(value => {
      if (active) { setData(value); setError('') }
    }).catch(reason => { if (active) { setError(String(reason)) } })

    return () => { active = false }
  }, [api, base, item.id, item.state, item.error, open])

  const load = async () => {
    try { setData(await api(`${base}/artifacts/${encodeURIComponent(item.id)}`)) } catch (reason) { setError(String(reason)) }
  }

  return <details onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer break-words">{kinds[item.kind] || item.kind} · {item.title || item.id} {item.state && `· ${states[item.state] || item.state}`}</summary>
    {error && <p role="alert">{error}<Button onClick={() => void load()} variant="ghost">重试读取</Button></p>}
    {data !== undefined && <><CopyButton label="复制此输入或产物" text={json(data)} /><LogView className="max-h-96">{json(data)}</LogView></>}
    {data === undefined && !error && <p>正在读取完整内容…</p>}
  </details>
}

export function TaskEvidence({ detail, api, base, ctx, refresh, error }: { detail: TaskDetail; api: Api; base: string; ctx: PluginContext; refresh: () => Promise<unknown>; error: (message: string) => void }) {
  const [onlyErrors, setOnlyErrors] = useState(false)
  const calls = detail.model_attempts
  const tokens = (call: ModelAttempt) => call.total_tokens ?? (typeof call.input_tokens === 'number' && typeof call.output_tokens === 'number' ? call.input_tokens + call.output_tokens : null)
  const known = calls.map(tokens).filter((value): value is number => value !== null)
  const events = detail.events.filter(event => !onlyErrors || hasError(event.data))

  return <div className="space-y-6">
    <section className="space-y-2"><h2 className="font-semibold">本步骤结果与历次尝试</h2>
      <p role="status">{states[detail.step.state] || detail.step.state}{detail.step.duration_ms !== undefined && ` · ${(detail.step.duration_ms / 1000).toFixed(1)} 秒`}</p>
      <p className="break-all text-xs text-muted-foreground">批次 {detail.run.id} · 规则 v{detail.run.version ?? '未知'} · {detail.run.day}</p>
      <p className="whitespace-pre-wrap">{detail.step.detail}</p>
      {detail.attempts.map((item, index) => <p key={item.id}>第 {index + 1} 次 · {states[item.state] || item.state} · {formatTimestamp(item.started)} · {item.detail}</p>)}
      <details><summary>完整步骤结果</summary><LogView>{json({ current: detail.step, original: detail.original_step })}</LogView></details>
    </section>
    <section className="space-y-2"><h2 className="font-semibold">模型调用与重试</h2>
      <p>实际尝试 {calls.length} 次（含重试）；已知 Token {known.reduce((a, b) => a + b, 0)}，未知回执 {calls.length - known.length} 次。</p>
      {!calls.length && <p className="text-muted-foreground">没有可读取的模型尝试记录；可能未调用模型，或历史记录未保存。</p>}
      {calls.map((call, index) => <div className="border-b py-2" key={call.id}>
        <p>尝试 {index + 1} · {call.model} · {call.provider} · {call.state === 'confirmed' ? '已收到结果' : states[call.state] || call.state} · {((call.received ? call.received - call.started : Date.now() / 1000 - call.started)).toFixed(1)} 秒</p>
        <p className="text-xs text-muted-foreground">{formatTimestamp(new Date(call.started * 1000).toISOString())} · Token：{tokens(call) ?? '未知'} {call.error_type}</p>
      </div>)}
    </section>
    <section className="space-y-2"><h2 className="font-semibold">输入、输出与保存产物</h2><p className="text-sm text-muted-foreground">{detail.trace_notice}</p>
      <details><summary>本批次规则快照</summary><LogView>{json(detail.policy ?? '历史批次未保存规则快照')}</LogView></details>
      {!detail.artifacts.length && <p>本任务尚无可读取的保存产物。</p>}
      {detail.artifacts.map(item => <ArtifactView api={api} base={base} item={item} key={`${base}:${item.id}`} />)}
    </section>
    <section className="space-y-3"><h2 className="font-semibold">实际执行时间线（已加载 {detail.events.length} 条）</h2>
      <label className="flex gap-2"><input checked={onlyErrors} onChange={event => setOnlyErrors(event.target.checked)} type="checkbox" />只看异常</label>
      {events.map(event => {
        const row = event.data as Record<string, unknown>
        const message = row && typeof row === 'object' ? row.detail || row.error || row.name || '' : ''

        return <details className="border-b py-2" key={event.id}>
          <summary className="cursor-pointer">{formatTimestamp(event.at)} · {eventNames[event.kind] || event.kind}{hasError(row) && ' · 待检查'} {String(message)}</summary>
          <CopyButton label={`复制事件 ${event.id}`} text={json(event)} /><LogView className="max-h-80">{json(event.data)}</LogView>
          {typeof row?.evidence_id === 'string' && <Screenshot api={api} identity={row.evidence_id} />}
        </details>
      })}
      {detail.more && <Button onClick={() => void refresh()} variant="outline">加载后续记录（自动刷新也会继续加载）</Button>}
    </section>
    {detail.actions.length > 0 && <section className="space-y-2"><h2 className="font-semibold">网页证据与人工核对</h2>
      <ActionManager ctx={ctx} onError={error} refresh={refresh} rows={detail.actions} />
    </section>}
  </div>
}
