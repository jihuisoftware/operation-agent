import { Button, CopyButton, formatTimestamp, host, type PluginContext } from '@hermes/plugin-sdk'
import { useState } from 'react'

import { LibraryPage } from '../library-page'
import { scopedContext } from '../workspace-state'

import { number, statuses, timestamp, useUsage } from './data'
import type { Page, UsageCall, UsageTask } from './types'
import { purposeLabel } from './visuals'

export function UsageTasks({ ctx, query }: { ctx: PluginContext; query: string }) {
  const [cursor, setCursor] = useState('')
  const { data, error } = useUsage<Page<UsageTask>>(ctx, `/usage/tasks?${query}&cursor=${encodeURIComponent(cursor)}`)

  return <section className="space-y-3"><h2 className="font-semibold">任务消耗 · 按 Token 降序</h2>
    {error && <p role="alert">{error}</p>}{!data && !error && <p>正在读取任务…</p>}
    {data?.items.length === 0 && <p className="text-muted-foreground">此范围没有模型调用。</p>}
    {data?.items.map(task => <TaskRow ctx={ctx} key={task.id} query={query} task={task} />)}
    <div className="flex gap-2">{cursor && <Button onClick={() => setCursor('')} variant="outline">返回第一页</Button>}{data?.cursor && <Button onClick={() => setCursor(data.cursor!)} variant="outline">下一页任务</Button>}</div>
  </section>
}

function TaskRow({ ctx, query, task }: { ctx: PluginContext; query: string; task: UsageTask }) {
  const [open, setOpen] = useState(false)
  const [original, setOriginal] = useState(false)
  const [error, setError] = useState('')
  const owner = host.state.requestOwner.get()

  return <details className="rounded border p-3" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer"><span className="font-medium">{purposeLabel(task.stage) || task.task_name}</span> · {number(task.total_tokens)} Token · {task.calls} 次调用 · {statuses[task.state] || task.state}<span className="ml-3 text-xs text-muted-foreground">{task.business_name} / {task.topic_name} · {formatTimestamp(timestamp(task.started))}</span></summary>
    {open && <div className="mt-3 space-y-3">
      <p className="text-xs text-muted-foreground">本次运行 {task.run_id || task.turn_id || task.id} · 输入 {number(task.prompt_tokens)} · 输出 {number(task.output_tokens)} · 缓存写入 {number(task.cache_write_tokens)} · 推理 {number(task.reasoning_tokens)}（已包含在输出中）</p>
      <CopyButton label="复制任务用量" text={JSON.stringify(task, null, 2)} />
      {task.session_id && <Button onClick={() => void host.openSession(task.session_id).catch(reason => setError(String(reason)))} variant="link">进入原会话</Button>}
      {task.run_id && task.business_id && task.topic_id && <Button onClick={() => setOriginal(value => !value)} variant="link">{original ? '收起原执行记录' : '查看原执行记录'}</Button>}
      {error && <p role="alert">{error}</p>}
      {original && <LibraryPage ctx={scopedContext(ctx, owner, { business_id: task.business_id, topic_id: task.topic_id })} record={task.run_id} section="history" />}
      <Calls ctx={ctx} query={query} task={task.id} />
    </div>}
  </details>
}

function Calls({ ctx, query, task }: { ctx: PluginContext; query: string; task: string }) {
  const [cursor, setCursor] = useState('')
  const { data, error } = useUsage<Page<UsageCall>>(ctx, `/usage/tasks/${encodeURIComponent(task)}/calls?${query}&cursor=${encodeURIComponent(cursor)}`)

  return <div className="space-y-2 overflow-x-auto">{error && <p role="alert">{error}</p>}
    <table className="w-full text-left text-xs"><thead><tr><th>步骤 / 用途</th><th>模型 / 提供方</th><th>回执时间</th><th>状态</th><th>Token</th><th>输入 / 输出</th></tr></thead><tbody>{data?.items.map(call => <tr className="border-b" key={call.id}><td className="py-2">{purposeLabel(call.purpose)}</td><td>{call.model || '未知模型'} / {call.provider || '未知提供方'}</td><td>{call.received ? formatTimestamp(timestamp(call.received)) : '等待回执'}</td><td>{statuses[call.state] || call.state}{call.error_type && ` · ${call.error_type}`}</td><td>{number(call.total_tokens)}</td><td>{number(call.prompt_tokens)} / {number(call.output_tokens)}</td></tr>)}</tbody></table>
    {cursor && <Button onClick={() => setCursor('')} variant="ghost">返回首批调用</Button>}{data?.cursor && <Button onClick={() => setCursor(data.cursor!)} variant="ghost">下一批调用</Button>}
  </div>
}
