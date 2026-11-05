import { Button, CopyButton, type CronBlueprintOwner, formatTimestamp, type PluginContext } from '@hermes/plugin-sdk'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { hasExternalActions } from './quick-selection'
import { type Run, states } from './records'
import { type TaskDetail, TaskEvidence } from './task-evidence'
import { TaskHelp, TaskPlan } from './task-help'

interface Props { ctx: PluginContext; owner: CronBlueprintOwner; task: string; runId: string | null; selectRun: (id: string) => void; back: () => void }
interface Catalog { version: number; policy: { modules: Record<string, boolean> }; tasks: { id: string; title: string; module: string }[]; execution?: { message: string }; browser_check_available?: boolean; task_details_available?: boolean }

export function DebugTaskPage({ ctx, owner, task, runId, selectRun, back }: Props) {
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [history, setHistory] = useState<Run[]>([])
  const [older, setOlder] = useState<number | null>(null)
  const [detail, setDetail] = useState<TaskDetail | null>(null)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [note, setNote] = useState('')
  const [notePending, setNotePending] = useState(false)

  const api = useMemo(() => <T,>(path: string, body?: unknown) => ctx.rest<T>(path, { owner,
    method: body === undefined ? 'GET' : 'POST', body, timeoutMs: body === undefined ? 20000 : 1_800_000 }), [ctx, owner])

  const scoped = useMemo(() => ({ ...ctx, rest: <T,>(path: string, options?: Parameters<PluginContext['rest']>[1]) => ctx.rest<T>(path, { ...options, owner }) }), [ctx, owner])
  const base = runId ? `/debug/${encodeURIComponent(runId)}/tasks/${task}` : ''
  const loadingSession = useMemo(() => ({ api, base, cursor: 0, generation: 0 }), [api, base])
  const busy = pending || Boolean(catalog?.execution)
  const description = catalog?.tasks.find(item => item.id === task)
  const enabled = description ? catalog?.policy.modules[description.module] : false
  const executeDisabled = busy || !enabled || !catalog?.task_details_available

  const refresh = useCallback(async () => {
    const generation = loadingSession.generation

    try {
      const next = await loadingSession.api<Catalog>('/debug')

      if (generation !== loadingSession.generation) { return }
      setCatalog(next)

      if (!next.task_details_available) { setError('后台尚未加载详细调试接口，请在当前任务结束后重启后台。');

 return }

      if (loadingSession.base) {
        const trace = await loadingSession.api<TaskDetail>(`${loadingSession.base}?after=${loadingSession.cursor}`)

        if (generation !== loadingSession.generation) { return }
        loadingSession.cursor = Math.max(loadingSession.cursor, trace.cursor)
        setDetail(previous => ({ ...trace, events: [...new Map([...(previous?.events || []), ...trace.events].map(event => [event.id, event])).values()].sort((a, b) => a.id - b.id) }))
        setHistory(previous => previous.some(item => item.id === trace.run.id)
          ? previous.map(item => item.id === trace.run.id ? { ...item, state: trace.run.state } : item)
          : [trace.run, ...previous])
      }

      setError('')
    } catch (reason) { if (generation === loadingSession.generation) { setError(String(reason)) } }
  }, [loadingSession])

  useEffect(() => {
    loadingSession.generation += 1
    loadingSession.cursor = 0
    setDetail(null)
    setNote('')
    let loading = false
    let active = true

    const poll = async () => {
      if (loading || !active) { return }
      loading = true

      try { await refresh() } finally { loading = false }
    }

    void poll()
    const timer = setInterval(() => void poll(), 2000)

    return () => { active = false; loadingSession.generation += 1; clearInterval(timer) }
  }, [refresh, loadingSession])

  useEffect(() => {
    let active = true
    setHistory([])
    setOlder(null)

    if (!catalog?.task_details_available) { return }
    void api<{ runs: Run[]; next: number | null }>(`/debug/tasks/${task}/runs`).then(value => {
      if (!active) { return }
      setHistory(value.runs); setOlder(value.next)

      if (!runId && value.runs[0]) { selectRun(value.runs[0].id) }
    }).catch(reason => { if (active) { setError(String(reason)) } })

    return () => { active = false }
  }, [api, task, runId, selectRun, catalog?.task_details_available])

  const execute = async (mode: 'normal' | 'quick') => {
    if (!catalog || busy) { return }
    const request = crypto.randomUUID()
    setPending(true); setError(''); selectRun(`debug:${request}`)

    try {
      await api('/debug/run', { task, mode, version: catalog.version, request_id: request,
        ...(mode === 'quick' && hasExternalActions([task]) ? { external_actions: 'execute_once' } : {}) })
    } catch (reason) { setError(String(reason)) } finally { setPending(false) }
  }

  const resume = async () => {
    if (!detail || busy) { return }
    setPending(true)

    try {
      await api(`/debug/${encodeURIComponent(detail.run.id)}/resume`, { request_id: crypto.randomUUID(), expected_revision: detail.run.revision,
        ...(detail.run.action_mode === 'execute_once' ? { external_actions: 'execute_once' } : {}) })
      await refresh()
    } catch (reason) { setError(String(reason)) } finally { setPending(false) }
  }

  const saveNote = async () => {
    setNotePending(true)

    try { await api(`${base}/notes`, { request_id: crypto.randomUUID(), text: note }); setNote(''); await refresh() }
    catch (reason) { setError(String(reason)) } finally { setNotePending(false) }
  }

  const loadOlder = async () => {
    try {
      const next = await api<{ runs: Run[]; next: number | null }>(`/debug/tasks/${task}/runs?before=${older}`)
      setHistory(previous => [...previous, ...next.runs]); setOlder(next.next)
    } catch (reason) { setError(String(reason)) }
  }

  return <main className="space-y-6 p-6">
    <Button onClick={back} variant="ghost">返回任务调试</Button>
    <h1 className="text-xl font-semibold">{description?.title || task} · 详细调试</h1>
    <TaskPlan task={task} />
    <div className="flex flex-wrap gap-2">
      <Button disabled={executeDisabled} onClick={() => void execute('normal')}>详细执行本任务</Button>
      <Button disabled={executeDisabled} onClick={() => void execute('quick')} variant="outline">快速实测本任务</Button>
      <Button onClick={() => void refresh()} variant="ghost">刷新记录</Button>
      {base && <CopyButton label="复制本任务完整记录" onCopyError={reason => setError(String(reason))} text={async () => JSON.stringify(await api(`${base}/export`), null, 2)}>复制本任务完整记录</CopyButton>}
    </div>
    <p className="text-xs text-muted-foreground">只执行当前任务，不自动执行其他模块。网页任务会真实提交；新建调试与继续原批次是不同操作。</p>
    {description && !enabled && <p>此模块尚未启用，请先在任务计划中启用，再进行单项调试。</p>}
    {catalog?.execution && <p role="status">{catalog.execution.message}</p>}
    {error && <p className="text-destructive" role="alert">{error}</p>}
    <section className="space-y-2"><h2 className="font-semibold">选择执行批次</h2>
      <select aria-label="选择执行批次" className="max-w-full rounded border bg-background p-2" onChange={event => selectRun(event.target.value)} value={runId || ''}>
        <option value="">尚未选择</option>
        {runId && !history.some(item => item.id === runId) && <option value={runId}>{runId}</option>}
        {history.map(item => <option key={item.id} value={item.id}>{formatTimestamp(item.started)} · {item.title} · {states[item.state] || item.state}</option>)}
      </select>
      {older && <Button onClick={() => void loadOlder()} variant="ghost">加载更早批次</Button>}
      {!runId && <p>还没有执行记录，可先按检查提示准备，再单独运行本任务。</p>}
    </section>
    <TaskHelp api={api} browserCheck={catalog?.browser_check_available} busy={busy} task={task} version={catalog?.version} />
    {detail?.run.state === 'paused' && <section className="space-y-2"><p>继续会恢复原批次的未完成项目，包含原批次中其他已选任务；不会改变原选择。</p>
      <Button disabled={busy} onClick={() => void resume()}>继续原批次未完成项目（真实执行）</Button></section>}
    {detail && <><TaskEvidence api={api} base={base} ctx={scoped} detail={detail} error={setError} refresh={refresh} />
      <section className="space-y-2"><h2 className="font-semibold">人工调试备注</h2><p className="text-xs text-muted-foreground">记录观察、检查结果与处理方法；备注不会修改执行状态或批准外部动作。</p>
        <textarea aria-label="人工调试备注" className="w-full rounded border bg-background p-2" maxLength={4000} onChange={event => setNote(event.target.value)} rows={4} value={note} />
        <Button disabled={notePending || !note.trim()} onClick={() => void saveNote()}>保存备注</Button>
        {detail.notes.map(item => <p className="whitespace-pre-wrap" key={item.id}>{formatTimestamp(item.created)} · {item.text}</p>)}
      </section></>}
  </main>
}
