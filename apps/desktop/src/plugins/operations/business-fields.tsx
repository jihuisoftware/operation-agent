import { Button, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@hermes/plugin-sdk'

import type { PolicyFieldsProps } from './blueprint-fields'
import type { BlueprintTemplate } from './blueprint-types'
import { adoptBusinessDefaults, selectBusinessSubtype } from './business-config'

export function BusinessFields({ policy, onChange, template }: PolicyFieldsProps & { template: BlueprintTemplate }) {
  return (
    <section aria-label="业务默认配置" className="mb-4 space-y-3">
      <p className="font-medium">业务主题：{template.title}</p>
      <label className="grid gap-2">
        业务子类
        <Select
          onValueChange={value => onChange(selectBusinessSubtype(policy, template, value === '__none__' ? '' : value))}
          value={policy.business_subtype || '__none__'}
        >
          <SelectTrigger aria-label="业务子类">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">暂不细分</SelectItem>
            {template.subtypes?.map(subtype => (
              <SelectItem key={subtype} value={subtype}>
                {subtype}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </label>
      <p>内容方向：{template.content_directions?.join('、')}</p>
      <p className="text-muted-foreground">
        补充实际品牌、产品或服务、所在地区和检索关键词。价格、资质和案例请使用已确认资料。
      </p>
      <div className="space-y-1">
        <p className="font-medium">常见咨询准备提示（需自行补充真实答案）</p>
        {template.questions?.map(question => (
          <p key={question}>{question}</p>
        ))}
      </div>
      <Button onClick={() => onChange(adoptBusinessDefaults(policy, template))} size="sm" variant="outline">
        采用此主题的内容配置
      </Button>
      <p className="text-xs text-muted-foreground">
        此按钮替换主题、目标、受众、风格与检索关键词；账号、素材、回复知识、授权、时间和额度保持原配置。
      </p>
    </section>
  )
}
