import { Checkbox } from '@hermes/plugin-sdk'

import type { Sharing, Template } from './analysis-types'
import { ChoiceField } from './configuration-choices'

export const defaultSharing: Sharing = { model_mode: 'summary', detail_fields: [], public_metrics: [] }

export function BusinessSharing({ value, onChange, template }: { value: Sharing; onChange: (value: Sharing) => void; template: Template }) {
  const toggle = (key: 'detail_fields' | 'public_metrics', field: string, enabled: boolean) => onChange({ ...value, [key]: enabled ? [...value[key], field] : value[key].filter(k => k !== field) })

  return <section aria-label="数据使用选项" className="space-y-4">
    <ChoiceField allowCustom={false} allowEmpty={false} label="模型可读取的数据" onChange={model_mode => onChange({ ...value, model_mode, detail_fields: [], public_metrics: model_mode === 'local' ? [] : value.public_metrics })} options={[{ value: 'summary', label: '仅汇总指标' }, { value: 'local', label: '仅本地使用' }, { value: 'details', label: '选择脱敏明细字段' }]} value={value.model_mode} />
    {value.model_mode === 'details' && <fieldset className="space-y-2"><legend>脱敏后发送的字段</legend><div className="flex flex-wrap gap-4">{Object.entries(template.fields).filter(([key]) => key !== 'key').map(([key, label]) => <label className="flex items-center gap-2" key={key}><Checkbox checked={value.detail_fields.includes(key)} onCheckedChange={v => toggle('detail_fields', key, v === true)} />{label}</label>)}</div>
      <p className="text-xs text-muted-foreground">身份字段不发送。自由文本默认不选，需检查下方脱敏预览。每次分析最多发送每个数据集 100 行，完整数据仍参与本地统计。</p></fieldset>}
    <fieldset className="space-y-2"><legend>允许对外文章使用的汇总指标</legend><div className="flex flex-wrap gap-4">{Object.entries(template.metrics).map(([key, label]) => <label className="flex items-center gap-2" key={key}><Checkbox checked={value.public_metrics.includes(key)} disabled={value.model_mode === 'local'} onCheckedChange={v => toggle('public_metrics', key, v === true)} />{label}</label>)}</div>
      <p className="text-xs text-muted-foreground">不选表示仅内部使用。模型分析权限与发布权限独立，原始明细不进入对外内容。</p></fieldset>
  </section>
}
