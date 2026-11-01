import { Button, type PluginContext, SegmentedControl } from '@hermes/plugin-sdk'
import { useState } from 'react'

import { GoalFields, ScheduleFields } from './blueprint-fields'
import {
  type BlueprintCatalog,
  type BlueprintPreview,
  type BlueprintTemplate,
  enableDefaultOperations,
  moduleLabels,
  seedBlueprint
} from './blueprint-types'
import { withTopicDefaults } from './business-config'
import { BusinessFields } from './business-fields'
import type { Policy } from './types'

interface WizardProps {
  ctx: PluginContext
  catalog: BlueprintCatalog
  template: BlueprintTemplate
  draft?: Policy
  onSaved: () => Promise<void>
  onAssets: () => void
}

const fieldLabels: Record<string, string> = {
  business_theme: '业务主题',
  business_subtype: '业务子类',
  modules: '执行模块',
  allowed: '动作授权',
  times: '执行时间',
  limits: '每日额度',
  topic: '主题',
  goal: '目标',
  brand: '项目／品牌',
  audience: '受众',
  style: '风格',
  account_id: '账号',
  timezone: '时区',
  sources: '网页来源',
  rss_sources: 'RSS',
  keywords: '关键词',
  knowledge: '回复知识',
  follow_terms: '回关条件',
  enabled: '启用状态',
  paused: '暂停状态',
  model_calls: '模型调用上限'
}

function changeValue(catalog: BlueprintCatalog, field: string, value: unknown) {
  if (field === 'business_theme') {
    return catalog.templates.find(t => t.id === value)?.title || (value ? String(value) : '未选择')
  }

  return JSON.stringify(value)
}

export function BlueprintWizard({ ctx, catalog, template, draft, onSaved, onAssets }: WizardProps) {
  const [baseVersion] = useState(catalog.version)
  const [policy, setPolicy] = useState(() => draft || seedBlueprint(catalog, template))
  const [step, setStep] = useState<'goal' | 'rules' | 'review'>('goal')
  const [preview, setPreview] = useState<BlueprintPreview | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [requestId, setRequestId] = useState(() => crypto.randomUUID())
  const business = catalog.templates.find(t => t.kind === 'business' && t.id === policy.business_theme)

  const change = (value: Policy) => {
    setPolicy(value)
    setPreview(null)
    setRequestId(crypto.randomUUID())
    setError('')
  }

  const review = async () => {
    setPending(true)
    setError('')

    try {
      const prepared = withTopicDefaults(policy)
      setPolicy(prepared)

      const result = await ctx.rest<BlueprintPreview>('/blueprints/preview', {
        method: 'POST',
        body: { version: baseVersion, policy: prepared }
      })

      setPreview(result)
      setStep('review')
    } catch (error) {
      setError(String(error))
    } finally {
      setPending(false)
    }
  }

  const save = async (mode: 'draft' | 'enable') => {
    if (mode === 'enable') {
      if (!preview) {
        await review()

        return
      }

      if (Object.keys(preview.missing).length > 0) {
        setError('暂不能启用，请先完善以下条件，或保存草稿稍后继续。')

        return
      }
    }

    setPending(true)
    setError('')

    try {
      await ctx.rest('/blueprints/apply', {
        method: 'POST',
        body: { version: baseVersion, policy: withTopicDefaults(policy), request_id: `${requestId}:${mode}`, mode }
      })
      await onSaved()
    } catch (error) {
      setError(String(error))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="space-y-5 text-sm">
      <div>
        <h2 className="text-base font-semibold">{template.title}</h2>
        <p className="mt-2 text-muted-foreground">{template.description}</p>
      </div>
      <SegmentedControl
        disabled={pending}
        onChange={next => {
          if (next === 'review') {
            void review()
          } else {
            setStep(next)
          }
        }}
        options={[
          { id: 'goal', label: '1 目标与模块' },
          { id: 'rules', label: '2 时间与规则' },
          { id: 'review', label: '3 检查与应用' }
        ]}
        value={step}
      />
      <fieldset className="contents" disabled={pending}>
        {step === 'goal' && (
          <>
            <details className="space-y-2">
              <summary className="cursor-pointer text-muted-foreground">使用默认完整流程</summary>
              <p className="text-muted-foreground">
                默认流程包含采集、资料整理、选题、内容生产、发布、评论、收到私信回复和日报。可按需关闭；回关单独开启。
              </p>
              <Button onClick={() => change(enableDefaultOperations(policy))} variant="outline">
                启用默认运营模块与授权
              </Button>
            </details>
            <GoalFields onChange={change} policy={policy} />
            {business && <BusinessFields onChange={change} policy={policy} template={business} />}
          </>
        )}
        {step === 'rules' && (
          <>
            <ScheduleFields onChange={change} policy={policy} />
            {(policy.modules.content || policy.modules.publish) && (
              <div className="space-y-2">
                <p>可用授权图片 {catalog.assets.filter(a => !a.revoked).length} 张。图片第一张作为封面。</p>
                <Button onClick={onAssets} variant="outline">
                  管理素材与内容版本
                </Button>
              </div>
            )}
          </>
        )}
        {step === 'review' && preview && (
          <div className="space-y-5">
            <div>
              <h3 className="font-medium">今日流程 · {policy.timezone}</h3>
              {preview.timeline.map(row => (
                <p className="mt-2" key={`${row.module}:${row.time}`}>
                  {row.time} · {row.label}
                </p>
              ))}
              <p className="mt-2 text-muted-foreground">
                每个模块只补最近一次到期任务，更早时段忽略且不记入历史；“立即执行”忽略排期，可重复执行。每日额度仍生效。
              </p>
            </div>
            <div>
              <h3 className="font-medium">预期产出</h3>
              {catalog.templates
                .filter(t => t.id !== 'daily' && policy.modules[t.id])
                .map(t => (
                  <p className="mt-2" key={t.id}>
                    {t.title}：{t.output}
                  </p>
                ))}
            </div>
            <div>
              <h3 className="font-medium">本次变更</h3>
              {preview.changes.length ? (
                preview.changes.map(row => (
                  <details className="mt-2" key={row.field}>
                    <summary>{fieldLabels[row.field] || row.field}</summary>
                    <p className="break-words text-muted-foreground">
                      原值：{changeValue(catalog, row.field, row.before)} → 新值：
                      {changeValue(catalog, row.field, row.after)}
                    </p>
                  </details>
                ))
              ) : (
                <p>规则内容没有变化。</p>
              )}
            </div>
            <p className="text-muted-foreground">
              发布和互动共享当前账号的每日额度。启用授权以本页所选动作为准，自动检查不代表人工审核。
            </p>
          </div>
        )}
      </fieldset>
      {error && (
        <p className="text-destructive" role="alert">
          {error}
        </p>
      )}
      {step === 'review' && preview && Object.keys(preview.missing).length > 0 && (
        <div className="space-y-2" role="alert">
          <h3 className="font-medium">启用前需要完善</h3>
          {Object.entries(preview.missing).map(([module, items]) => (
            <p key={module}>
              {moduleLabels[module] || '运营计划'}：{items.join('；')}
            </p>
          ))}
          <p className="text-muted-foreground">补全条件后重新检查，也可返回取消暂不执行的模块。</p>
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={pending}
              onClick={() => {
                setError('')
                setStep('goal')
              }}
              variant="outline"
            >
              修改目标与模块
            </Button>
            <Button
              disabled={pending}
              onClick={() => {
                setError('')
                setStep('rules')
              }}
              variant="outline"
            >
              完善时间与规则
            </Button>
          </div>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Button disabled={pending} onClick={() => void save('draft')} variant="outline">
          保存草稿
        </Button>
        {step === 'goal' && (
          <Button disabled={pending} onClick={() => setStep('rules')}>
            下一步：时间与规则
          </Button>
        )}
        {step === 'rules' && (
          <Button disabled={pending} onClick={() => void review()}>
            检查与预览
          </Button>
        )}
        {step === 'review' && (
          <Button disabled={pending} onClick={() => void save('enable')}>
            {pending ? '正在应用…' : '应用并启用'}
          </Button>
        )}
      </div>
    </div>
  )
}
