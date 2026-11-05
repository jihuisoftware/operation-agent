import { Button, CopyButton, type CronBlueprintOwner, formatTimestamp, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'

import { BrowserCheck } from './browser-check'
import { hasExternalActions, QuickSelection } from './quick-selection'
import { DebugRecord, type Detail, type Run, states } from './records'
import { DebugTaskPage } from './task-page'
import { type DebugTask, DebugTaskRow, type TaskStatus } from './task-row'

interface Catalog {
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

      try {
        const next = await api<Catalog>('/debug')

        if (!disposed) { setCatalog(next); setLoadError('') }

        if (selected && next.runs.some(run => run.id === selected)) {
          const log = await api<Detail>(`/debug/${encodeURIComponent(selected)}`)

          if (!disposed) { setDetail(log) }
        }

        failures = 0
      } catch (reason) {
        failures += 1

        if (failures >= 3) { clearInterval(timer) }

        if (!disposed) { setLoadError(String(reason)) }
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
    setSelected(`debug:${requestId}`)
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

  return (
    <main className="space-y-6 overflow-auto p-6">
      <h1 className="text-xl font-semibold">任务调试 · 仅开发环境</h1>
      <p>每次只执行所选任务，忽略原排期。每次点击是独立批次；详细和快速两种模式都只执行下方勾选的项目；单项按钮仅执行所在行。</p>
      <p>勾选图文发布时，由自动检查代替人工审核，立即真实发布本次稿件，最多 1 次；不会开启日常自动审核。</p>
      <p className="text-muted-foreground">调试会调用真实业务流程。网页任务使用当前内嵌账号；可在实时画面中暂停并人工接管。</p>
      <p className="text-xs text-muted-foreground">所有开发调试均不限制模型调用次数，不占用正常运营的每日模型额度；Token 用量和实际费用仍照常记录。外部动作的“快速实测”按钮只授权该项真实执行 1 次；多选快速实测中每种所选外部动作最多 1 次。本次授权不会写入日常自动运营计划。</p>
      {(error || loadError) && <div><p className="text-destructive" role="alert">{error || loadError}</p><CopyButton label="复制请求错误" text={JSON.stringify({ owner, run_id: selected, error, loadError }, null, 2)}>复制请求错误</CopyButton></div>}
      {loadError && <Button onClick={() => setRevision(value => value + 1)} variant="outline">重新连接调试服务</Button>}
      {catalog?.execution && <p className="text-sm text-muted-foreground" role="status">{catalog.execution.message}</p>}
      {catalog?.browser_check_available && <BrowserCheck busy={busy} onCheck={() => api('/debug/browser-check', { version: catalog.version, request_id: crypto.randomUUID() })} />}
      {!catalog && <p>请在当前 Profile 的 config.yaml 设置 development.operations_debug: true，并使用源码 Server 和开发版 Desktop。</p>}
      <section className="space-y-3 rounded-xl bg-muted/40 p-4">
        {catalog && <QuickSelection available={catalog.selective_pipeline_available === true} busy={busy} onRun={(tasks, mode) => void run('pipeline', mode, tasks)} tasks={catalog.tasks} />}
      </section>
      <p className="text-xs text-muted-foreground">下方单项按钮不使用上方勾选。每行右侧显示近期调试状态、步骤说明和耗时，每 2 秒刷新；最近批次未选择的项目会明确标注。点击状态可查看对应批次详情。</p>
      {catalog && !catalog.task_details_available && <p className="text-sm text-muted-foreground">后台尚未加载详细调试接口，请在当前任务结束后重启后台，再进入任务子页面。</p>}
      {typeof catalog?.web_block_reason === 'string' && <p className="text-xs text-muted-foreground">当前网页控制：{catalog.web_block_reason || '未处于人工接管'}。下方保留最近一次运行结果；草稿生成完成不等于已满足发布条件。</p>}
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
      <section className="space-y-3">
        <h2 className="font-semibold">调试记录</h2>
        <p className="text-xs text-muted-foreground">时间按当前电脑的本地时区显示，精确到秒。</p>
        {catalog?.runs.length === 0 && <p>尚无调试记录。</p>}
        {catalog?.runs.map(item => <Button key={item.id} onClick={() => { setSelected(item.id); setDetail(null) }} variant="ghost">
          {item.title} · {states[item.state] || item.state} · <time dateTime={item.started} title={item.started}>{formatTimestamp(item.started)}</time>
        </Button>)}
      </section>
      {catalog?.runs.filter(item => item.state === 'paused').map(item => <div className="space-y-2" key={`resume:${item.id}`}>
        <p>{item.title}已暂停：{item.detail}</p>
        <p className="text-sm text-muted-foreground">继续原批次的未完成项目；上方勾选仅用于新批次，不会改变这次续跑。</p>
        <Button disabled={busy} onClick={() => void resume(item)} variant="outline">{item.selected_tasks ? '继续原批次所选项目（真实执行）' : '继续历史批次未完成项目（真实执行）'}</Button>
      </div>)}
      {detail && <DebugRecord detail={detail} />}
    </main>
  )
}
