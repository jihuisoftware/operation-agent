import { Button, CopyButton, type CronBlueprintOwner, formatTimestamp, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useEffect, useMemo, useState } from 'react'

interface Run {
  id: string
  title: string
  state: string
  started: string
  detail: string
  duration_ms?: number
}
interface Catalog {
  version: number
  policy: { modules: Record<string, boolean> }
  tasks: { id: string; title: string; module: string }[]
  runs: Run[]
}
interface Detail {
  run: Run
  events: { id: number; at: string; kind: string; data: unknown }[]
  actions: unknown[]
}
const states: Record<string, string> = { running: '正在执行', completed: '完成', failed: '失败', skipped: '跳过', needs_attention: '待完善', interrupted: '已中断' }

export function DebugPage({ ctx }: { ctx: PluginContext }) {
  const owner = useValue(host.state.requestOwner)

  return <DebugPanel ctx={ctx} key={JSON.stringify(owner)} owner={owner} />
}

export function DebugPanel({ ctx, owner }: { ctx: PluginContext; owner: CronBlueprintOwner }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [error, setError] = useState('')
  const [loadError, setLoadError] = useState('')
  const [pending, setPending] = useState(false)
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

  const run = async (task: string) => {
    if (!catalog) { return }
    const requestId = crypto.randomUUID()
    setPending(true)
    setError('')
    setSelected(`debug:${requestId}`)
    setDetail(null)

    try {
      await api('/debug/run', { task, version: catalog.version, request_id: requestId })
    } catch (reason) { setError(`${String(reason)}；请先查看执行记录核对结果，再决定是否重新执行。`) } finally {
      setPending(false)
      setRevision(value => value + 1)
    }
  }

  const busy = pending || catalog?.runs.some(item => item.state === 'running')

  return (
    <main className="space-y-6 overflow-auto p-6">
      <h1 className="text-xl font-semibold">任务调试 · 仅开发环境</h1>
      <p>每次只执行所选任务，忽略原排期。每次点击是独立批次；仍遵守模块、授权、暂停和每日额度。</p>
      <p className="text-muted-foreground">调试会调用真实业务流程。网页任务使用当前内嵌账号；可在实时画面中暂停并人工接管。</p>
      {(error || loadError) && <p className="text-destructive" role="alert">{error || loadError}</p>}
      {loadError && <Button onClick={() => setRevision(value => value + 1)} variant="outline">重新连接调试服务</Button>}
      {!catalog && <p>请在当前 Profile 的 config.yaml 设置 development.operations_debug: true，并使用源码 Server 和开发版 Desktop。</p>}
      <div className="space-y-3">
        {catalog?.tasks.map(task => (
          <div className="flex items-center justify-between gap-4" key={task.id}>
            <span>{task.title}{!catalog.policy.modules[task.module] && ' · 未启用模块'}</span>
            <Button disabled={Boolean(busy)} onClick={() => void run(task.id)} variant="outline">单独执行{task.title}</Button>
          </div>
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
      {detail && <section className="space-y-3">
        <div className="flex items-center gap-3"><h2 className="font-semibold">{detail.run.title} · {states[detail.run.state] || detail.run.state}</h2><CopyButton label="复制完整记录" text={JSON.stringify(detail, null, 2)}>复制完整记录</CopyButton></div>
        <p className="whitespace-pre-wrap">{detail.run.detail}</p>
        {detail.run.duration_ms !== undefined && <p>执行耗时：{detail.run.duration_ms} 毫秒</p>}
        {detail.events.map(event => <details key={event.id} open={detail.run.state === 'running'}>
          <summary><time dateTime={event.at} title={event.at}>{formatTimestamp(event.at)}</time> · {event.kind}</summary>
          <pre className="whitespace-pre-wrap break-words text-xs">{JSON.stringify(event.data, null, 2)}</pre>
        </details>)}
        <details><summary>外部动作及结果（{detail.actions.length}）</summary><pre className="whitespace-pre-wrap break-words text-xs">{JSON.stringify(detail.actions, null, 2)}</pre></details>
      </section>}
    </main>
  )
}
