import { Button, CopyButton, type CronBlueprintOwner, formatTimestamp, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useEffect, useMemo, useState } from 'react'

import { DebugRecord, type Detail, type Run, states } from './records'
import { type DebugTask, DebugTaskRow, type TaskStatus } from './task-row'

interface Catalog {
  version: number
  policy: { modules: Record<string, boolean> }
  tasks: DebugTask[]
  task_status?: Record<string, TaskStatus>
  runs: Run[]
  pipeline_available?: boolean
  web_block_reason?: string
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
  const [pending, setPending] = useState<{ task: string; id: string } | null>(null)
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
    setPending({ task, id: `debug:${requestId}` })
    setError('')
    setSelected(`debug:${requestId}`)
    setDetail(null)

    try {
      await api('/debug/run', { task, mode, version: catalog.version, request_id: requestId,
        ...(mode === 'quick' ? { external_actions: 'execute_once' } : {}) })
    } catch (reason) { setError(`${String(reason)}；请先查看执行记录核对结果，再决定是否重新执行。`) } finally {
      setPending(null)
      setRevision(value => value + 1)
    }
  }

  const busy = Boolean(pending) || Boolean(catalog?.runs.some(item => item.state === 'running'))

  return (
    <main className="space-y-6 overflow-auto p-6">
      <h1 className="text-xl font-semibold">任务调试 · 仅开发环境</h1>
      <p>每次只执行所选任务，忽略原排期。每次点击是独立批次；详细执行遵守当前模块、授权、暂停、采集与外部动作额度，快速整链路按下方覆盖规则运行。</p>
      <p className="text-muted-foreground">调试会调用真实业务流程。网页任务使用当前内嵌账号；可在实时画面中暂停并人工接管。</p>
      <p className="text-xs text-muted-foreground">所有开发调试均不限制模型调用次数，不占用正常运营的每日模型额度；Token 用量和实际费用仍照常记录。外部动作的“快速实测”按钮只授权该项真实执行 1 次；快速整链路每种外部动作最多 1 次。本次授权不会写入日常自动运营计划。</p>
      {(error || loadError) && <div><p className="text-destructive" role="alert">{error || loadError}</p><CopyButton label="复制请求错误" text={JSON.stringify({ owner, run_id: selected, error, loadError }, null, 2)}>复制请求错误</CopyButton></div>}
      {loadError && <Button onClick={() => setRevision(value => value + 1)} variant="outline">重新连接调试服务</Button>}
      {!catalog && <p>请在当前 Profile 的 config.yaml 设置 development.operations_debug: true，并使用源码 Server 和开发版 Desktop。</p>}
      <section className="space-y-3 rounded-xl bg-muted/40 p-4">
        <h2 className="font-semibold">整链路测试</h2>
        <p>采集 → 整理归类 → 选题 → 内容生产 → 发布 → 评论与回复 → 私信 → 回关 → 日报</p>
        <p className="text-sm text-muted-foreground">按当前规则真实执行，采集与外部动作仍受现有额度约束，模型调用次数不限。未启用、未授权或缺少条件的步骤会注明原因；失败阻止依赖步骤，发布只使用本轮草稿。最后保存调试日报，不受日报模块开关影响。</p>
        <div className="flex flex-wrap gap-2">
          <Button disabled={Boolean(busy) || !catalog?.pipeline_available} onClick={() => void run('pipeline')}>开始整链路测试（真实执行）</Button>
          <Button disabled={Boolean(busy) || !catalog?.pipeline_available} onClick={() => void run('pipeline', 'quick')} variant="outline">快速实测整条链路（真实执行）</Button>
        </div>
        <p className="text-xs text-muted-foreground">快速模式仅抽样 1 条来源、检索最多 1 次，模型调用次数不限；发布、评论、回复、私信和回关直接走正式流程，每种最多 1 次。仍检查模块、账号、素材、回复知识、暂停和每日动作额度；没有条件或候选时说明原因，结果不明时只核对、不重发。</p>
        {catalog && !catalog.pipeline_available && <p className="text-sm text-muted-foreground">请重启源码 Server，加载整链路调试接口。</p>}
      </section>
      <p className="text-xs text-muted-foreground">每行右侧显示近期调试状态、当前步骤说明和耗时，每 2 秒刷新。点击状态可查看对应批次详情。</p>
      {typeof catalog?.web_block_reason === 'string' && <p className="text-xs text-muted-foreground">当前网页控制：{catalog.web_block_reason || '未处于人工接管'}。下方保留最近一次运行结果；草稿生成完成不等于已满足发布条件。</p>}
      <div>
        {catalog?.tasks.map(task => (
          <DebugTaskRow
            busy={busy}
            enabled={catalog.policy.modules[task.module]}
            key={task.id}
            onInspect={id => { setSelected(id); setDetail(null) }}
            onRun={mode => void run(task.id, mode)}
            stale={Boolean(loadError)}
            status={catalog.task_status?.[task.id]}
            submitting={Boolean(pending && (pending.task === 'pipeline' || pending.task === task.id) && catalog.task_status?.[task.id]?.run_id !== pending.id)}
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
      {detail && <DebugRecord detail={detail} />}
    </main>
  )
}
