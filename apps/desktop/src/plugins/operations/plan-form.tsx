import { Button, Checkbox, Codicon, host, useValue } from '@hermes/plugin-sdk'

import { GoalFields, ScheduleFields } from './blueprint-fields'
import { actionLabels, type BlueprintCatalog } from './blueprint-types'
import { withTopicDefaults } from './business-config'
import { ChoiceField, choices } from './configuration-choices'
import { goalChoices, themeChoices } from './configuration-presets'
import { selectBusiness, selectMode, workMode, type WorkMode } from './plan-config'
import type { Policy } from './types'

interface Props {
  catalog: BlueprintCatalog
  policy: Policy
  change: (policy: Policy) => void
}

export function PlanForm({ catalog, policy, change }: Props) {
  const model = useValue(host.state.model)
  const businesses = catalog.templates.filter(t => t.kind === 'business')
  const selected = businesses.find(t => t.id === policy.business_theme)

  return (
    <>
      {(catalog.model_ready === false || !model) && (
        <div className="flex flex-wrap items-center gap-3 bg-muted/40 p-3">
          <Codicon name="plug" />
          <span>连接模型后才能生成分析与内容；现在可以先保存计划。</span>
          <Button onClick={() => host.navigate('/settings?tab=providers')} variant="outline">
            连接模型
          </Button>
        </div>
      )}
      <div className="grid gap-4 @[36rem]:grid-cols-2">
        <ChoiceField
          label="业务类型"
          onChange={value => change(selectBusiness(policy, catalog, value))}
          options={businesses.map(t => ({ value: t.id, label: t.title }))}
          value={policy.business_theme === 'custom' ? policy.business_subtype || '' : policy.business_theme || ''}
        />
        <ChoiceField
          clearPresetOnCustom
          label="具体主题"
          onChange={topic => change({ ...policy, topic })}
          options={selected ? choices(selected.content_directions || []) : themeChoices}
          placeholder="填写你想运营的具体方向，例如：小户型收纳、机械零件加工"
          value={policy.topic}
        />
      </div>
      <p className="text-xs text-muted-foreground">修改名称会保留当前主题的资料与历史；独立运营新方向请在左侧新增主题。</p>
      <ChoiceField
        allowCustom={false}
        allowEmpty={false}
        label="工作方式"
        onChange={value => change(selectMode(policy, value as WorkMode))}
        options={[
          { value: 'research', label: '研究分析' },
          { value: 'content', label: '准备内容' },
          { value: 'automatic', label: '自动运营' },
          ...(workMode(policy) === 'custom' ? [{ value: 'custom', label: '自定义组合（保留当前设置）' }] : [])
        ]}
        value={workMode(policy)}
      />
      <div className="flex flex-wrap gap-4">
        {Object.entries(actionLabels)
          .filter(
            ([action]) =>
              action !== 'source' && action !== 'publish' && policy.modules[{ comment: 'comments', reply: 'comments' }[action] || action]
          )
          .map(([action, label]) => (
            <label className="flex items-center gap-2" key={action}>
              <Checkbox
                checked={policy.allowed[action]}
                onCheckedChange={value =>
                  change({ ...policy, allowed: { ...policy.allowed, [action]: value === true } })
                }
              />
              允许{label}
            </label>
          ))}
      </div>
      <p className="text-xs text-muted-foreground">
        {withTopicDefaults(policy).goal || '选择主题后自动填写基础目标'} · {policy.audience || '相关受众'} ·{' '}
        {policy.style}
      </p>
      <details className="space-y-4">
        <summary className="cursor-pointer">常用设置 · 目标、执行时间与每日数量</summary>
        <ChoiceField
          label="运营目标"
          onChange={goal => change({ ...policy, goal })}
          options={goalChoices}
          value={policy.goal}
        />
        <ScheduleFields level="common" onChange={change} policy={policy} />
      </details>
      <details className="space-y-4">
        <summary className="cursor-pointer">详细设置 · 风格、功能、信息源与回复知识</summary>
        <GoalFields onChange={change} policy={policy} />
        <ScheduleFields level="advanced" onChange={change} policy={policy} />
        <Button onClick={() => host.navigate('/analysis')} variant="link">
          分析范围设置
        </Button>
        <Button onClick={() => host.navigate('/materials?tab=assets')} variant="link">
          管理授权素材
        </Button>
      </details>
    </>
  )
}
