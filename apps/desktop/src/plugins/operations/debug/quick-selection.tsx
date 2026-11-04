import { Button, Checkbox, SegmentedControl } from '@hermes/plugin-sdk'
import { useState } from 'react'

import type { DebugTask } from './task-row'

const externalTasks = new Set(['publish', 'comment', 'reply', 'dm', 'follow'])
export const hasExternalActions = (tasks: string[]) => tasks.some(id => externalTasks.has(id))

export type ExecutionMode = 'normal' | 'quick'

interface Props {
  tasks: DebugTask[]
  busy: boolean
  available: boolean
  onRun: (tasks: string[], mode: ExecutionMode) => void
}

export function QuickSelection({ tasks, busy, available, onRun }: Props) {
  const [selected, setSelected] = useState<string[]>([])
  const [mode, setMode] = useState<ExecutionMode>('quick')
  const ordered = tasks.filter(task => selected.includes(task.id)).map(task => task.id)
  const disabled = busy || !available
  const toggle = (id: string, checked: boolean) => setSelected(current => checked ? [...current, id] : current.filter(value => value !== id))

  return <fieldset className="space-y-3">
    <legend className="font-medium">本次执行项目</legend>
    <div aria-label="执行模式" className="space-y-2" role="group">
      <SegmentedControl disabled={disabled} onChange={setMode} options={[{ id: 'quick', label: '快速模式' }, { id: 'normal', label: '详细模式' }]} value={mode} />
      <p className="text-xs text-muted-foreground">{mode === 'quick' ? '快速模式仅抽样采集；所选外部动作每种最多真实执行 1 次。' : '详细模式按已保存的模块、授权和额度执行；同样只执行勾选项目。'}</p>
    </div>
    <p className="text-sm text-muted-foreground">只执行本次勾选的项目，不自动补选上游。未选上游时复用现有有效资料或草稿；缺少条件的项目会跳过并说明原因。</p>
    <div className="flex flex-wrap gap-2">
      <Button disabled={disabled} onClick={() => setSelected(tasks.map(task => task.id))} variant="outline">全选</Button>
      <Button disabled={disabled} onClick={() => setSelected([])} variant="outline">清空</Button>
      <Button disabled={disabled} onClick={() => setSelected(tasks.filter(task => !externalTasks.has(task.id)).map(task => task.id))} variant="outline">仅内部</Button>
    </div>
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {tasks.map(task => <label className="flex items-center gap-2" key={task.id}>
        <Checkbox aria-label={task.title} checked={selected.includes(task.id)} disabled={disabled} onCheckedChange={checked => toggle(task.id, checked === true)} />
        {task.title}
      </label>)}
    </div>
    <p className="text-sm">已选 {ordered.length} 项</p>
    {mode === 'quick' && hasExternalActions(ordered) && <p className="text-sm text-muted-foreground">所选外部动作将直接与生产交互，每种最多执行 1 次；仅对本次选择授权，不改变日常计划。</p>}
    <p className="text-xs text-muted-foreground">快速模式采集仅抽样 1 条来源、检索最多 1 次；两种模式的模型调用次数均不限，仍检查模块、账号、素材、知识、暂停和每日动作额度。勾选“运营日报”才执行业务日报；未勾选时仍保存本批次诊断摘要。</p>
    {!available && <p className="text-sm text-muted-foreground">当前后台尚不支持统一按勾选项目执行，请更新并重启后台后再使用。</p>}
    <Button disabled={disabled || ordered.length === 0} onClick={() => onRun(ordered, mode)} variant="outline">执行所选项目（真实执行）</Button>
  </fieldset>
}
