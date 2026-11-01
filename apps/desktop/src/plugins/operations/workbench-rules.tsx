import { Button, Checkbox } from '@hermes/plugin-sdk'

import { GoalFields, type PolicyFieldsProps, ScheduleFields } from './blueprint-fields'

export function WorkbenchRules({ policy, onChange, onSave }: PolicyFieldsProps & { onSave: () => void }) {
  return <div className="max-w-3xl space-y-5">
    <GoalFields onChange={onChange} policy={policy} />
    <details className="space-y-4">
      <summary className="cursor-pointer font-medium">时间、资料与动作规则</summary>
      <ScheduleFields onChange={onChange} policy={policy} />
    </details>
    <div className="flex flex-wrap gap-4">
      <label className="flex items-center gap-2"><Checkbox checked={policy.enabled} onCheckedChange={value => onChange({ ...policy, enabled: value === true })} />启用运营计划</label>
      <label className="flex items-center gap-2"><Checkbox checked={policy.paused} onCheckedChange={value => onChange({ ...policy, paused: value === true })} />暂停执行</label>
    </div>
    <Button onClick={onSave}>保存规则与时间表</Button>
  </div>
}
