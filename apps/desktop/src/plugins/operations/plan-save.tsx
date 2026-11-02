import { Button } from '@hermes/plugin-sdk'

import type { BlueprintPreview } from './blueprint-types'
import { replacesSavedValue } from './use-plan-editor'

const fields: Record<string, string> = {
  topic: '运营主题',
  goal: '运营目标',
  audience: '目标受众',
  style: '内容风格',
  brand: '品牌',
  modules: '功能选择',
  allowed: '动作开关',
  limits: '每日额度',
  times: '执行时间',
  timezone: '时区',
  sources: '网页来源',
  rss_sources: 'RSS',
  keywords: '关键词',
  knowledge: '回复知识',
  follow_terms: '回关条件',
  model_calls: '模型额度',
  business_theme: '业务类型',
  business_subtype: '业务子类',
  account_id: '目标账号',
  deadline: '截止日期',
  priority: '优先级'
}

interface Props {
  confirm: boolean
  preview: BlueprintPreview | null
  busy: boolean
  notice: string
  first: boolean
  save: (start: boolean) => Promise<void>
}

export function PlanSave({ confirm, preview, busy, notice, first, save }: Props) {
  const disabled = busy || !preview || Boolean(preview.blocking?.length)

  return (
    <>
      {confirm && (
        <div className="space-y-2" role="status">
          <p>本次将更新以下已保存配置，请核对后再次保存：</p>
          {preview?.changes.filter(replacesSavedValue).map(c => (
            <details key={c.field}>
              <summary>{fields[c.field] || c.field}</summary>
              <pre className="whitespace-pre-wrap break-words text-xs">
                {JSON.stringify(c.before, null, 2)} → {JSON.stringify(c.after, null, 2)}
              </pre>
            </details>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Button disabled={disabled || Boolean(notice)} onClick={() => void save(true)}>
          {busy ? '正在保存…' : first ? '开始运营' : '保存并运行快速首轮'}
        </Button>
        <Button disabled={disabled} onClick={() => void save(false)} variant="outline">
          {first ? '保存，稍后开始' : '保存设置'}
        </Button>
      </div>
    </>
  )
}
