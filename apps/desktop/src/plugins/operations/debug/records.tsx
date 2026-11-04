import { Codicon, CopyButton, formatTimestamp, LogView } from '@hermes/plugin-sdk'

export interface Step {
  id: string
  title: string
  state: string
  detail: string
  started?: string
  duration_ms?: number
}
export interface Run {
  id: string
  title: string
  state: string
  started: string
  detail: string
  duration_ms?: number
  steps?: Step[]
  version?: number
  day?: string
  model_quota?: 'unlimited'
  revision?: number
  attempt?: number
  action_mode?: string
  selected_tasks?: string[]
  diagnostic_report?: { id: string }
  coverage?: { quick?: boolean; read_limit?: number; query_limit?: number; external_actions?: string }
}
export interface Detail {
  run: Run
  events: { id: number; at: string; kind: string; data: unknown }[]
  actions: unknown[]
}
export const states: Record<string, string> = { pending: '等待执行', running: '正在执行', completed: '完成', failed: '失败', skipped: '跳过', needs_attention: '待检查', interrupted: '已中断', paused: '已暂停' }
const problemStates = new Set(['failed', 'paused', 'interrupted', 'needs_attention', 'unknown', 'blocked', 'unavailable', 'submitted'])
const icons: Record<string, string> = { completed: 'pass', running: 'loading', failed: 'error', needs_attention: 'warning' }
const json = (value: unknown) => JSON.stringify(value, null, 2)

export function hasError(value: unknown): boolean {
  if (!value || typeof value !== 'object') { return false }
  const row = value as Record<string, unknown>

  return Boolean(row.error || row.traceback || row.error_code || row.phase === 'failed' || problemStates.has(String(row.state))) || Object.values(row).some(item => typeof item === 'object' && hasError(item))
}

export function errorLog(detail: Detail) {
  return {
    run: { id: detail.run.id, title: detail.run.title, started: detail.run.started, state: detail.run.state, version: detail.run.version, day: detail.run.day, selected_tasks: detail.run.selected_tasks },
    steps: detail.run.steps?.filter(hasError) || [],
    events: detail.events.filter(event => hasError(event.data)),
    actions: detail.actions.filter(hasError)
  }
}

export function DebugRecord({ detail }: { detail: Detail }) {
  const errors = errorLog(detail)
  const hasErrors = errors.steps.length + errors.events.length + errors.actions.length > 0

  return <section className="space-y-4">
    <div className="flex flex-wrap items-center gap-3">
      <h2 className="font-semibold">{detail.run.title} · {states[detail.run.state] || detail.run.state}</h2>
      <CopyButton label="复制完整记录" text={() => json(detail)}>复制完整记录</CopyButton>
      {hasErrors && <CopyButton label="仅复制错误日志" text={() => json(errors)}>仅复制错误日志</CopyButton>}
    </div>
    <p className="whitespace-pre-wrap">{detail.run.detail}</p>
    {detail.run.selected_tasks && <p className="text-sm">本次所选项目（{detail.run.selected_tasks.length} 项）：{detail.run.selected_tasks.map(id => detail.run.steps?.find(step => step.id === id)?.title || id).join('、')}</p>}
    {detail.run.diagnostic_report && <p className="text-xs text-muted-foreground">本批次诊断摘要已保存，不计为所选业务步骤。</p>}
    {detail.run.model_quota === 'unlimited' && <p className="text-sm text-muted-foreground">本次调试模型调用次数不限，用量照常记录，不占正常运营模型额度。</p>}
    {detail.run.action_mode === 'execute_once' && <p className="text-sm text-muted-foreground">本次快速实测使用真实生产流程，每种外部动作最多 1 次；本次授权不改变日常计划。</p>}
    {detail.run.coverage?.external_actions === 'readiness_only' && <p className="text-sm text-muted-foreground">此历史批次仅预检查外部动作，未实际执行。</p>}
    {detail.run.duration_ms !== undefined && <p>执行耗时：{detail.run.duration_ms} 毫秒</p>}
    {detail.run.steps?.map((step, index) => {
      const events = detail.events.filter(event => (event.data as { step_id?: string })?.step_id === step.id)

      return <details className="space-y-2" key={step.id} open={step.state === 'running' || problemStates.has(step.state)}>
        <summary className="cursor-pointer">{index + 1}. {step.title} · <Codicon name={icons[step.state] || 'circle-outline'} spinning={step.state === 'running'} /> {states[step.state] || step.state}{step.duration_ms !== undefined && ` · ${(step.duration_ms / 1000).toFixed(1)} 秒`}</summary>
        <p className="whitespace-pre-wrap">{step.detail}</p>
        <CopyButton label={`复制${step.title}日志`} text={json({ run_id: detail.run.id, step, events })}>复制本步骤日志</CopyButton>
        <LogView className="max-h-80">{json({ step, events })}</LogView>
      </details>
    })}
    <details open={!detail.run.steps}>
      <summary className="cursor-pointer">完整事件（{detail.events.length}）</summary>
      <div className="space-y-3">
        {detail.events.map(event => <details key={event.id}>
          <summary className="cursor-pointer"><time dateTime={event.at} title={event.at}>{formatTimestamp(event.at)}</time> · {event.kind}{hasError(event.data) && ' · 异常'}</summary>
          <CopyButton label={`复制日志 ${event.id}`} text={json({ run_id: detail.run.id, ...event })}>{hasError(event.data) ? '复制这块错误日志' : '复制这条日志'}</CopyButton>
          <LogView className="max-h-80">{json(event.data)}</LogView>
        </details>)}
      </div>
    </details>
    <details><summary className="cursor-pointer">外部动作及结果（{detail.actions.length}）</summary><LogView className="max-h-80">{json(detail.actions)}</LogView></details>
  </section>
}
