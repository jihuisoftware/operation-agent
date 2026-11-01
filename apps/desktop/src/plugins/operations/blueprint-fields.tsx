import { Checkbox, Input, Textarea } from '@hermes/plugin-sdk'

import { AccountSelection } from './account-selection'
import { actionLabels, actionModules, moduleLabels } from './blueprint-types'
import { ChoiceField, choices, KeywordChoices, TimeSlots } from './configuration-choices'
import { audienceChoices, goalChoices, priorityChoices, styleChoices, themeChoices, timezoneChoices } from './configuration-presets'
import type { Policy } from './types'

export interface PolicyFieldsProps {
  policy: Policy
  onChange: (policy: Policy) => void
}

export function GoalFields({ policy, onChange }: PolicyFieldsProps) {
  return (
    <div className="space-y-4">
      <ChoiceField label="运营主题" onChange={topic => onChange({ ...policy, topic })} options={themeChoices} placeholder="例如：小户型厨房收纳" value={policy.topic} />
      <p className="text-xs text-muted-foreground">从常用主题开始，或选“自定义／手动添加”填写具体主题。</p>
      <details className="space-y-3">
        <summary className="cursor-pointer text-muted-foreground">细化范围（可选）</summary>
        <ChoiceField label="运营目标" onChange={goal => onChange({ ...policy, goal })} options={goalChoices} value={policy.goal} />
        <p className="text-xs text-muted-foreground">目标未选择时，保存会按运营主题生成基础目标。</p>
        <label className="grid gap-2">项目／品牌<Input onChange={event => onChange({ ...policy, brand: event.target.value })} value={policy.brand} /></label>
        <ChoiceField label="目标受众" onChange={audience => onChange({ ...policy, audience })} options={audienceChoices} value={policy.audience} />
        <ChoiceField label="内容风格" onChange={style => onChange({ ...policy, style })} options={styleChoices} value={policy.style} />
      </details>
      <h3 className="font-medium">需要执行哪些模块</h3>
      <p className="text-xs text-muted-foreground">采集保存原文，整理模块分类并提炼依据，选题与内容使用整理资料；各环节可独立启停。</p>
      <div className="grid gap-3 sm:grid-cols-2">
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
    </div>
  )
}

export function ScheduleFields({ policy, onChange }: PolicyFieldsProps) {
  const update = (key: keyof Policy, value: unknown) => onChange({ ...policy, [key]: value })
  const external = ['publish', 'comments', 'dm', 'follow'].some(m => policy.modules[m])
  const lists: [keyof Policy, string][] = []

  if (policy.modules.research) {
    lists.push(['sources', '网页地址'], ['rss_sources', 'RSS / Atom'])
  }

  if (policy.modules.dm) {
    lists.push(['knowledge', '已确认回复知识'])
  }

  if (policy.modules.follow) {
    lists.push(['follow_terms', '回关匹配条件'])
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">执行时间使用：{timezoneChoices.find(choice => choice.value === policy.timezone)?.label || policy.timezone}</p>
      {Object.entries(moduleLabels)
        .filter(([m]) => policy.modules[m])
        .map(([m, label]) => (
          <TimeSlots key={m} label={label} onChange={times => update('times', { ...policy.times, [m]: times })} values={policy.times[m] || []} />
        ))}
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="grid gap-2">截止日期（可选）<Input onChange={event => update('deadline', event.target.value)} type="date" value={policy.deadline.slice(0, 10)} /><span className="text-xs text-muted-foreground">不选日期表示长期运营</span></label>
        <ChoiceField allowCustom={false} allowEmpty={false} label="目标优先级" onChange={value => update('priority', Number(value))} options={priorityChoices} value={String(policy.priority)} />
      </div>
      {external && <AccountSelection onChange={onChange} policy={policy} />}
      <details className="space-y-3" open={policy.modules.dm || policy.modules.follow || undefined}>
        <summary className="cursor-pointer">来源与回复资料（采集可直接按主题检索）</summary>
      {policy.modules.research && <KeywordChoices onChange={keywords => update('keywords', keywords)} values={policy.keywords} />}
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
      </details>
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
      <details className="space-y-3">
        <summary className="cursor-pointer">每日额度与时区</summary>
        <ChoiceField allowEmpty={false} label="时区" onChange={value => update('timezone', value)} options={timezoneChoices} value={policy.timezone} />
      {Object.entries(policy.limits)
        .filter(([a]) => (a === 'source' ? policy.modules.research : policy.modules[actionModules[a]]))
        .map(([action, value]) => (
          <ChoiceField key={action} label={`${actionLabels[action]}每日上限`} max={action === 'source' ? 10000 : 1000} onChange={next => update('limits', { ...policy.limits, [action]: Number(next) })}
            options={choices((action === 'source' ? [0, 30, 100, 500, 1000, 5000, 10000] : [0, 1, 3, 5, 10, 20, 50, 100, 1000]).map(String))}
            type="number" value={String(value)} />
        ))}
      <ChoiceField label="每日模型调用上限" max={1000} onChange={value => update('model_calls', Number(value))} options={choices([0, 10, 50, 100, 500, 1000].map(String))} type="number" value={String(policy.model_calls)} />
      </details>
    </div>
  )
}
