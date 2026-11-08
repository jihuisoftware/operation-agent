import { Button, CopyButton, type CronBlueprintOwner, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'

import { BrowserCheck } from './browser-check'
import { DebugHistory } from './history'
import { hasExternalActions, QuickSelection } from './quick-selection'
import { type Detail, type Run } from './records'
import { DebugTaskPage } from './task-page'
import { type DebugTask, DebugTaskRow, type TaskStatus } from './task-row'

interface Catalog {
  cancel_all_available?: boolean
  history_clear_available?: boolean
  task_details_available?: boolean
  browser_check_available?: boolean
  version: number
  policy: { modules: Record<string, boolean> }
  tasks: DebugTask[]
  task_status?: Record<string, TaskStatus>
  runs: Run[]
  execution?: { message: string; started?: string; progress_at?: string } | null
  selective_pipeline_available?: boolean
  web_block_reason?: string
}

export function DebugPage({ ctx }: { ctx: PluginContext }) {
  const owner = useValue(host.state.requestOwner)
  const [params, setParams] = useSearchParams()

  const openTask = useCallback((task: string, run?: string) => setParams(previous => {
    const next = new URLSearchParams(previous)
    next.set('task', task)

    if (run) { next.set('run', run) } else { next.delete('run') }

    return next
  }), [setParams])

  const selectRun = useCallback((id: string) => setParams(previous => {
    const next = new URLSearchParams(previous)
    next.set('run', id)

    return next
  }), [setParams])

  const back = () => setParams(previous => {
    const next = new URLSearchParams(previous)
    next.delete('task'); next.delete('run')

    return next
  })

  const task = params.get('task')

  return task ? <DebugTaskPage back={back} ctx={ctx} key={`${JSON.stringify(owner)}:${task}`} owner={owner} runId={params.get('run')} selectRun={selectRun} task={task} />
    : <DebugPanel ctx={ctx} key={JSON.stringify(owner)} onOpenTask={openTask} owner={owner} />
}

export function DebugPanel({ ctx, owner, onOpenTask }: { ctx: PluginContext; owner: CronBlueprintOwner; onOpenTask?: (task: string, run?: string) => void }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [error, setError] = useState('')
  const [loadError, setLoadError] = useState('')
  const [pending, setPending] = useState<{ task: string; id: string; tasks?: string[] } | null>(null)
  const [revision, setRevision] = useState(0)
  const [clearing, setClearing] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [notice, setNotice] = useState('')
  const generation = useRef(0)

  const api = useMemo(() => <T,>(path: string, body?: unknown) => ctx.rest<T>(path, {
    owner, method: body ? 'POST' : 'GET', body, timeoutMs: body ? 1_800_000 : 15000
  }), [ctx, owner])

  useEffect(() => {
    let disposed = false
    let busy = false
    let failures = 0
    let timer: ReturnType<typeof setInterval>

    const refresh = async () => {
      if (busy) { return }
      busy = true
      const current = generation.current

      try {
        const next = await api<Catalog>('/debug')

        if (!disposed && current === generation.current) { setCatalog(next); setLoadError('') }

        if (current === generation.current && selected && next.runs.some(run => run.id === selected)) {
          const log = await api<Detail>(`/debug/${encodeURIComponent(selected)}`)

          if (!disposed && current === generation.current) { setDetail(log) }
        }

        failures = 0
      } catch (reason) {
        failures += 1

        if (failures >= 3) { clearInterval(timer) }

        if (!disposed && current === generation.current) { setLoadError(String(reason)) }
      } finally { busy = false }
    }

    void refresh()
    timer = setInterval(() => void refresh(), 2000)

    return () => { disposed = true; clearInterval(timer) }
  }, [api, selected, revision])

  const run = async (task: string, mode: 'normal' | 'quick' = 'normal', tasks?: string[]) => {
    if (!catalog) { return }

    if (task === 'pipeline' && (catalog.selective_pipeline_available !== true || !tasks?.length)) { return }
    const requestId = crypto.randomUUID()
    setPending({ task, id: `debug:${requestId}`, ...(tasks ? { tasks } : {}) })
    setError('')
    setSelected(null)
    setDetail(null)

    try {
      await api('/debug/run', { task, mode, version: catalog.version, request_id: requestId,
        ...(tasks ? { tasks } : {}),
        ...(mode === 'quick' && hasExternalActions(tasks || [task]) ? { external_actions: 'execute_once' } : {}) })
    } catch (reason) {
      const message = String(reason)

      if (message.includes('本次调试未启动') || message.includes('已有任务执行中')) {
        setError(message.includes('本次调试未启动') ? message : `${message}；本次调试未启动，请等待当前任务结束后重试。`)
        setSelected(null)
      } else { setError(`${message}；请先查看执行记录核对结果，再决定是否重新执行。`) }
    } finally {
      setPending(null)
      setRevision(value => value + 1)
    }
  }

  const resume = async (item: Run) => {
    setPending({ task: 'pipeline', id: item.id, tasks: item.selected_tasks })
    setSelected(item.id)
    setError('')

    try {
      await api(`/debug/${encodeURIComponent(item.id)}/resume`, {
        request_id: crypto.randomUUID(), expected_revision: item.revision,
        ...(item.action_mode === 'execute_once' ? { external_actions: 'execute_once' } : {})
      })
    } catch (reason) { setError(String(reason)) } finally {
      setPending(null)
      setRevision(value => value + 1)
    }
  }

  const currentBatch = catalog?.runs.find(item => item.state === 'running') || catalog?.runs[0]
  const currentSelection = pending ? pending.tasks : currentBatch?.selected_tasks
  const busy = Boolean(pending) || Boolean(catalog?.execution) || Boolean(catalog?.runs.some(item => item.state === 'running'))

  const clearHistory = async () => {
    if (clearing || !catalog?.history_clear_available) { return }
    setClearing(true); setError(''); setNotice('')
    generation.current += 1

    try {
      const result = await ctx.rest<{ cleared: number; retained: number }>('/debug/history/clear', {
        owner, method: 'POST', body: {}, timeoutMs: 15000
      })

      generation.current += 1
      setSelected(null); setDetail(null)
      setNotice(`已清除 ${result.cleared} 条历史记录，保留 ${result.retained} 条未结束记录。`)
      const next = await api<Catalog>('/debug')
      setCatalog(next)
    } catch (reason) { setError(String(reason)) }
    finally { setClearing(false); setRevision(value => value + 1) }
  }

  const cancelAll = async () => {
    if (cancelling || clearing || !catalog?.cancel_all_available) { return }
    setCancelling(true); setError(''); setNotice('')
    generation.current += 1

    try {
      const result = await ctx.rest<{ cancelled: number; detail: string }>('/debug/cancel-all', {
        owner, method: 'POST', body: { request_id: crypto.randomUUID() }, timeoutMs: 15000
      })

      generation.current += 1
      setNotice(`已取消 ${result.cancelled} 个批次。${result.detail}`)
    } catch (reason) { setError(String(reason)) }
    finally { setCancelling(false); setRevision(value => value + 1) }
  }

  return (
    <main className="space-y-6 overflow-auto p-6">
      <h1 className="text-xl font-semibold">任务调试 · 仅开发环境</h1>
      {(error || loadError) && <div><p className="text-destructive" role="alert">{error || loadError}</p><CopyButton label="复制请求错误" text={JSON.stringify({ owner, run_id: selected, error, loadError }, null, 2)}>复制请求错误</CopyButton></div>}
      {loadError && <Button onClick={() => setRevision(value => value + 1)} variant="outline">重新连接调试服务</Button>}
      {catalog?.execution && <p className="text-sm text-muted-foreground" role="status">{catalog.execution.message}</p>}
      {catalog?.browser_check_available && <BrowserCheck busy={busy} onCheck={() => api('/debug/browser-check', { version: catalog.version, request_id: crypto.randomUUID() })} />}
      {!catalog && <p>请在当前 Profile 的 config.yaml 设置 development.operations_debug: true，并使用源码 Server 和开发版 Desktop。</p>}
      <section className="space-y-3 rounded-xl bg-muted/40 p-4">
        {catalog && <QuickSelection available={catalog.selective_pipeline_available === true} busy={busy} onRun={(tasks, mode) => void run('pipeline', mode, tasks)} tasks={catalog.tasks} />}
      </section>
      {catalog && !catalog.task_details_available && <p className="text-sm text-muted-foreground">后台尚未加载详细调试接口，请在当前任务结束后重启后台，再进入任务子页面。</p>}

      <div>
        {catalog?.tasks.map(task => (
          <DebugTaskRow
            busy={busy}
            detailsAvailable={catalog.task_details_available === true}
            enabled={catalog.policy.modules[task.module]}
            key={task.id}
            notSelected={Boolean(currentSelection && !currentSelection.includes(task.id))}
            onInspect={id => { setSelected(id); setDetail(null) }}
            onOpen={() => onOpenTask ? onOpenTask(task.id, catalog.task_status?.[task.id]?.run_id) : host.navigate(`/operations-debug?task=${task.id}`)}
            onRun={mode => void run(task.id, mode)}
            stale={Boolean(loadError)}
            status={catalog.task_status?.[task.id]}
            submitting={Boolean(pending && (pending.task === task.id || (pending.task === 'pipeline' && (!pending.tasks || pending.tasks.includes(task.id)))) && catalog.task_status?.[task.id]?.run_id !== pending.id)}
            task={task}
          />
        ))}
      </div>
      <DebugHistory cancelAvailable={catalog?.cancel_all_available === true} cancelling={cancelling}
        clearAvailable={catalog?.history_clear_available === true} clearing={clearing} detail={detail}
        notice={notice} onCancel={() => void cancelAll()} onClear={() => void clearHistory()} onSelect={id => { setSelected(id); setDetail(null) }}
        runs={catalog?.runs || []} selected={selected} />
    </main>
  )
}
