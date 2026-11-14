import { Button, host, Input, Textarea, useMutation } from '@hermes/plugin-sdk'
import { useState } from 'react'

import { linkTask, patchTask, unlinkTask } from './api'
import type { KanbanTaskDetail } from './types'
import { errText } from './ui'

interface TaskEditingProps {
  detail: KanbanTaskDetail
  onUpdated: () => void
}

export function TaskEditing({ detail, onUpdated }: TaskEditingProps) {
  const task = detail.task
  const [title, setTitle] = useState(task.title)
  const [priority, setPriority] = useState(String(task.priority ?? 0))
  const save = useMutation({
    mutationFn: () => patchTask(task.id, { title: title.trim(), priority: Number(priority) }),
    onSuccess: onUpdated,
    onError: error => host.notify({ kind: 'error', message: errText(error) })
  })
  return (
    <details className="space-y-2 rounded border p-3">
      <summary className="cursor-pointer text-sm">编辑任务与人工审核</summary>
      <label className="block text-xs">
        标题
        <Input value={title} onChange={e => setTitle(e.target.value)} />
      </label>
      <label className="block text-xs">
        优先级
        <Input type="number" value={priority} onChange={e => setPriority(e.target.value)} />
      </label>
      <Button
        size="xs"
        disabled={save.isPending || !title.trim() || !Number.isFinite(Number(priority))}
        onClick={() => save.mutate()}
      >
        保存任务信息
      </Button>
      <Completion task={task} onUpdated={onUpdated} />
      <Dependencies detail={detail} onUpdated={onUpdated} />
    </details>
  )
}

function Completion({ task, onUpdated }: { task: KanbanTaskDetail['task']; onUpdated: () => void }) {
  const [result, setResult] = useState(task.result ?? '')
  const complete = useMutation({
    mutationFn: (status: string) => patchTask(task.id, { status, result: result.trim(), summary: result.trim() }),
    onSuccess: onUpdated,
    onError: error => host.notify({ kind: 'error', message: errText(error) })
  })
  if (task.status === 'running') {
    return <p className="text-xs">任务正在执行。需修改执行结果时，请先停止任务。</p>
  }
  return (
    <div className="space-y-2 border-t pt-2">
      <label className="block text-xs">
        完成结果 / 审核说明
        <Textarea value={result} onChange={e => setResult(e.target.value)} />
      </label>
      <Button
        size="xs"
        disabled={complete.isPending || (!result.trim() && task.status !== 'review')}
        onClick={() => complete.mutate('done')}
      >
        确认完成
      </Button>
      {task.status === 'ready' && (
        <Button
          size="xs"
          variant="outline"
          disabled={complete.isPending || !result.trim()}
          onClick={() => complete.mutate('review')}
        >
          转入人工审核
        </Button>
      )}
    </div>
  )
}

function Dependencies({ detail, onUpdated }: TaskEditingProps) {
  const [parent, setParent] = useState('')
  const mutation = useMutation({
    mutationFn: (remove: string | null) =>
      remove ? unlinkTask(remove, detail.task.id) : linkTask(parent.trim(), detail.task.id),
    onSuccess: () => {
      setParent('')
      onUpdated()
    },
    onError: error => host.notify({ kind: 'error', message: errText(error) })
  })
  return (
    <div className="space-y-2 border-t pt-2">
      <label className="block text-xs">
        前置任务 ID
        <Input value={parent} onChange={e => setParent(e.target.value)} />
      </label>
      <Button size="xs" disabled={mutation.isPending || !parent.trim()} onClick={() => mutation.mutate(null)}>
        添加依赖
      </Button>
      {detail.links.parents.map(id => (
        <div key={id} className="flex items-center gap-2 text-xs">
          <span>{detail.link_tasks?.find(task => task.id === id)?.title ?? id}</span>
          <Button size="xs" variant="ghost" disabled={mutation.isPending} onClick={() => mutation.mutate(id)}>
            解除依赖
          </Button>
        </div>
      ))}
    </div>
  )
}
