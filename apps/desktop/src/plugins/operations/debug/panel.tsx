import { Button, CopyButton, type CronBlueprintOwner, formatTimestamp, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useEffect, useMemo, useState } from 'react'

import { DebugRecord, type Detail, type Run, states } from './records'

interface Catalog {
  version: number
  policy: { modules: Record<string, boolean> }
  tasks: { id: string; title: string; module: string }[]
  runs: Run[]
  pipeline_available?: boolean
}

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

  const run = async (task: string, mode: 'normal' | 'quick' = 'normal') => {
    if (!catalog) { return }
    const requestId = crypto.randomUUID()
    setPending(true)
    setError('')
    setSelected(`debug:${requestId}`)
    setDetail(null)

    try {
      await api('/debug/run', { task, mode, version: catalog.version, request_id: requestId })
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
      {(error || loadError) && <div><p className="text-destructive" role="alert">{error || loadError}</p><CopyButton label="复制请求错误" text={JSON.stringify({ owner, run_id: selected, error, loadError }, null, 2)}>复制请求错误</CopyButton></div>}
      {loadError && <Button onClick={() => setRevision(value => value + 1)} variant="outline">重新连接调试服务</Button>}
      {!catalog && <p>请在当前 Profile 的 config.yaml 设置 development.operations_debug: true，并使用源码 Server 和开发版 Desktop。</p>}
      <section className="space-y-3 rounded-xl bg-muted/40 p-4">
        <h2 className="font-semibold">整链路测试</h2>
        <p>采集 → 整理归类 → 选题 → 内容生产 → 发布 → 评论与回复 → 私信 → 回关 → 日报</p>
        <p className="text-sm text-muted-foreground">按当前规则真实执行，消耗现有额度。未启用、未授权或缺少条件的步骤会注明原因；失败阻止依赖步骤，发布只使用本轮草稿。最后保存调试日报，不受日报模块开关影响。</p>
        <div className="flex flex-wrap gap-2">
          <Button disabled={Boolean(busy) || !catalog?.pipeline_available} onClick={() => void run('pipeline')}>开始整链路测试（真实执行）</Button>
          <Button disabled={Boolean(busy) || !catalog?.pipeline_available} onClick={() => void run('pipeline', 'quick')} variant="outline">快速调试整条链路</Button>
        </div>
        <p className="text-xs text-muted-foreground">快速调试每个阶段最多执行一次，采集最多读取 1 条、检索 1 次，模型调用最多 2 次；仍遵守当前授权，外部动作可能真实提交。</p>
        {catalog && !catalog.pipeline_available && <p className="text-sm text-muted-foreground">请重启源码 Server，加载整链路调试接口。</p>}
      </section>
      <div className="space-y-3">
        {catalog?.tasks.map(task => (
          <div className="flex items-center justify-between gap-4" key={task.id}>
            <span>{task.title}{!catalog.policy.modules[task.module] && ' · 未启用模块'}</span>
            <div className="flex gap-2"><Button disabled={Boolean(busy)} onClick={() => void run(task.id)} variant="outline">详细执行{task.title}</Button><Button disabled={Boolean(busy)} onClick={() => void run(task.id, 'quick')} variant="ghost">快速调试</Button></div>
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
      {detail && <DebugRecord detail={detail} />}
    </main>
  )
}
