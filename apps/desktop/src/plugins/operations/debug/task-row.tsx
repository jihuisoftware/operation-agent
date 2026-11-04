import { Button, Codicon } from '@hermes/plugin-sdk'

import { states } from './records'

export interface DebugTask {
  id: string
  title: string
  module: string
}

export interface TaskStatus {
  run_id: string
  state: string
  detail: string
  duration_ms?: number
}

interface Props {
  task: DebugTask
  enabled: boolean
  busy: boolean
  status?: TaskStatus
  submitting: boolean
  stale: boolean
  notSelected?: boolean
  onRun: (mode: 'normal' | 'quick') => void
  onInspect: (id: string) => void
}

const icons: Record<string, string> = { running: 'loading', submitting: 'loading', completed: 'pass', failed: 'error', needs_attention: 'warning', interrupted: 'warning', skipped: 'circle-slash' }
const labels: Record<string, string> = { ...states, submitting: '等待接收', idle: '暂无近期记录', not_selected: '本次未选择' }

function presentation({ status, submitting, notSelected }: Pick<Props, 'status' | 'submitting' | 'notSelected'>) {
  if (notSelected) { return { state: 'not_selected', detail: '本次批次未选择此项目，未发起执行', elapsed: '' } }

  return {
    state: submitting ? 'submitting' : status?.state || 'idle',
    detail: submitting ? '正在提交调试请求' : status?.detail,
    elapsed: !submitting && status?.duration_ms != null ? `${(status.duration_ms / 1000).toFixed(1)} 秒` : ''
  }
}

export function DebugTaskRow({ task, enabled, busy, status, submitting, stale, notSelected = false, onRun, onInspect }: Props) {
  const { state, detail, elapsed } = presentation({ status, submitting, notSelected })

  const content = <>
    <span aria-label={`${task.title}调试状态`} className={`flex items-center justify-end gap-1.5 ${state === 'failed' ? 'text-destructive' : ''}`} role="status">
      <Codicon name={icons[state] || 'circle-outline'} spinning={!stale && (state === 'running' || state === 'submitting')} />
      {labels[state] || state}{elapsed && <span className="text-xs text-muted-foreground">· {elapsed}</span>}
      {stale && <span className="text-xs text-muted-foreground">· 状态待刷新</span>}
    </span>
    {detail && <span className="line-clamp-2 max-w-full break-words text-xs text-muted-foreground" title={detail}>{detail}</span>}
  </>

  return <div aria-label={task.title} className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b py-3 last:border-b-0" role="group">
    <span className="min-w-40 flex-1">{task.title}{!enabled && ' · 未启用模块'}</span>
    <div className="flex gap-2"><Button aria-label={`详细执行${task.title}`} disabled={busy} onClick={() => onRun('normal')} variant="outline">详细执行此项</Button><Button aria-label={`快速实测${task.title}（真实执行）`} disabled={busy} onClick={() => onRun('quick')} variant="ghost">快速实测此项</Button></div>
    <div className="ml-auto w-80 min-w-0 max-w-full text-right">
      {status && !submitting && !notSelected
        ? <Button aria-label={`查看${task.title}调试详情`} className="h-auto w-full flex-col items-end gap-1 whitespace-normal py-1 font-normal" onClick={() => onInspect(status.run_id)} variant="ghost">{content}</Button>
        : <div className="space-y-1 px-3 py-1">{content}</div>}
    </div>
  </div>
}
