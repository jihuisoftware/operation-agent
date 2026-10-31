import { Checkbox, Input, Textarea } from '@hermes/plugin-sdk'

import { actionLabels, actionModules, moduleLabels } from './blueprint-types'
import type { Policy } from './types'

export interface PolicyFieldsProps {
  policy: Policy
  onChange: (policy: Policy) => void
}

export function GoalFields({ policy, onChange }: PolicyFieldsProps) {
  return (
    <div className="space-y-4">
      {(
        [
          ['topic', '运营主题'],
          ['goal', '运营目标'],
          ['brand', '项目／品牌'],
          ['audience', '目标受众'],
          ['style', '内容风格']
        ] as const
      ).map(([key, label]) => (
        <label className="grid gap-2" key={key}>
          {label}
          <Input onChange={e => onChange({ ...policy, [key]: e.target.value })} value={policy[key]} />
        </label>
      ))}
      <p className="text-muted-foreground">选择加入当前计划的模块；取消选择只停止后续执行，保留历史记录。</p>
      {Object.entries(moduleLabels).map(([module, label]) => (
        <label className="flex items-center gap-2" key={module}>
          <Checkbox
            checked={policy.modules[module]}
            onCheckedChange={value => onChange({ ...policy, modules: { ...policy.modules, [module]: value === true } })}
          />
          {label}
        </label>
      ))}
    </div>
  )
}

export function ScheduleFields({ policy, onChange }: PolicyFieldsProps) {
  const update = (key: keyof Policy, value: unknown) => onChange({ ...policy, [key]: value })
  const external = ['publish', 'comments', 'dm', 'follow'].some(m => policy.modules[m])
  const lists: [keyof Policy, string][] = []

  if (policy.modules.research) {
    lists.push(['sources', '网页地址'], ['rss_sources', 'RSS / Atom'], ['keywords', '检索关键词'])
  }

  if (policy.modules.dm) {
    lists.push(['knowledge', '已确认回复知识'])
  }

  if (policy.modules.follow) {
    lists.push(['follow_terms', '回关匹配条件'])
  }

  return (
    <div className="space-y-4">
      <label className="grid gap-2">
        时区
        <Input onChange={e => update('timezone', e.target.value)} value={policy.timezone} />
      </label>
      {Object.entries(moduleLabels)
        .filter(([m]) => policy.modules[m])
        .map(([m, label]) => (
          <label className="grid gap-2" key={m}>
            {label}时间（多个时间用逗号分隔）
            <Input
              onChange={e => update('times', { ...policy.times, [m]: e.target.value.split(',').map(s => s.trim()) })}
              value={policy.times[m].join(',')}
            />
          </label>
        ))}
      {external && (
        <label className="grid gap-2">
          小红书账号 ID
          <Input onChange={e => update('account_id', e.target.value)} value={policy.account_id} />
        </label>
      )}
      {lists.map(([key, label]) => (
        <label className="grid gap-2" key={key}>
          {label}（每行一条）
          <Textarea
            onBlur={() => update(key, (policy[key] as string[]).map(s => s.trim()).filter(Boolean))}
            onChange={e => update(key, e.target.value.split('\n'))}
            rows={3}
            value={(policy[key] as string[]).join('\n')}
          />
        </label>
      ))}
      {Object.entries(actionModules)
        .filter(([, m]) => policy.modules[m])
        .map(([action]) => (
          <label className="flex items-center gap-2" key={action}>
            <Checkbox
              checked={policy.allowed[action]}
              onCheckedChange={value => update('allowed', { ...policy.allowed, [action]: value === true })}
            />
            允许{actionLabels[action]}
          </label>
        ))}
      {Object.entries(policy.limits)
        .filter(([a]) => (a === 'source' ? policy.modules.research : policy.modules[actionModules[a]]))
        .map(([action, value]) => (
          <label className="grid gap-2" key={action}>
            {actionLabels[action]}每日上限
            <Input
              max={1000}
              min={0}
              onChange={e => update('limits', { ...policy.limits, [action]: Number(e.target.value) })}
              type="number"
              value={value}
            />
          </label>
        ))}
      <label className="grid gap-2">
        每日模型调用上限
        <Input
          max={1000}
          min={0}
          onChange={e => update('model_calls', Number(e.target.value))}
          type="number"
          value={policy.model_calls}
        />
      </label>
    </div>
  )
}
