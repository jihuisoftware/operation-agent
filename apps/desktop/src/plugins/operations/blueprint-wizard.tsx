import { Button, type PluginContext, SegmentedControl } from '@hermes/plugin-sdk'
import { useState } from 'react'

import { GoalFields, ScheduleFields } from './blueprint-fields'
import {
  type BlueprintCatalog,
  type BlueprintPreview,
  type BlueprintTemplate,
  moduleLabels,
  seedBlueprint
} from './blueprint-types'
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

export function BlueprintWizard({ ctx, catalog, template, draft, onSaved, onAssets }: WizardProps) {
  const [baseVersion] = useState(catalog.version)
  const [policy, setPolicy] = useState(() => draft || seedBlueprint(catalog, template))
  const [step, setStep] = useState<'goal' | 'rules' | 'review'>('goal')
  const [preview, setPreview] = useState<BlueprintPreview | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [requestId, setRequestId] = useState(() => crypto.randomUUID())

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
      const result = await ctx.rest<BlueprintPreview>('/blueprints/preview', {
        method: 'POST',
        body: { version: baseVersion, policy }
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
    setPending(true)
    setError('')

    try {
      await ctx.rest('/blueprints/apply', {
        method: 'POST',
        body: { version: baseVersion, policy, request_id: `${requestId}:${mode}`, mode }
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
        {step === 'goal' && <GoalFields onChange={change} policy={policy} />}
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
              <p className="mt-2 text-muted-foreground">过期时段不会集中补发；启用后按保存的规则执行。</p>
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
            {Object.keys(preview.missing).length > 0 && (
              <div role="alert">
                <h3 className="font-medium">需要完善</h3>
                {Object.entries(preview.missing).map(([module, items]) => (
                  <p key={module}>
                    {moduleLabels[module] || '运营计划'}：{items.join('；')}
                  </p>
                ))}
              </div>
            )}
            <div>
              <h3 className="font-medium">本次变更</h3>
              {preview.changes.length ? (
                preview.changes.map(row => (
                  <details className="mt-2" key={row.field}>
                    <summary>{fieldLabels[row.field] || row.field}</summary>
                    <p className="break-words text-muted-foreground">
                      原值：{JSON.stringify(row.before)} → 新值：{JSON.stringify(row.after)}
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
          <Button
            disabled={pending || !preview || Object.keys(preview.missing).length > 0}
            onClick={() => void save('enable')}
          >
            {pending ? '正在应用…' : '应用并启用'}
          </Button>
        )}
      </div>
    </div>
  )
}
