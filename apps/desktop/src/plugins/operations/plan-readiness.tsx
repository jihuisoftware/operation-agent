import { Badge, Button, Codicon, host } from '@hermes/plugin-sdk'

import { moduleLabels } from './blueprint-types'

export interface Readiness {
  waiting_upstream?: boolean
  selected: boolean
  ready: boolean
  reasons: string[]
  action: string
  after?: string
}

export function PlanReadiness({ rows }: { rows: Record<string, Readiness> }) {
  const selected = Object.entries(rows).filter(([, row]) => row.selected)

  return (
    <section aria-label="运行条件" className="grid gap-4 @[36rem]:grid-cols-2">
      <div className="space-y-2">
        <h3 className="flex items-center gap-2 font-medium">
          <Codicon name="check" />
          现在可以做
        </h3>
        <div className="flex flex-wrap gap-2">
          {selected
            .filter(([, row]) => row.ready && !row.waiting_upstream)
            .map(([key]) => (
              <Badge key={key} variant="muted">
                {moduleLabels[key]}
              </Badge>
            ))}
        </div>
        <div className="flex flex-wrap gap-2">
          {selected
            .filter(([, row]) => row.ready && row.waiting_upstream)
            .map(([key]) => (
              <Badge key={key} variant="muted">
                {moduleLabels[key]} · 等待上游产出
              </Badge>
            ))}
        </div>
        <p className="text-xs text-muted-foreground">
          各步骤依次执行，等待上游资料时会记录原因；网页动作还需执行器在线。
        </p>
      </div>
      <div className="space-y-2">
        <h3 className="flex items-center gap-2 font-medium">
          <Codicon name="checklist" />
          稍后需要补充
        </h3>
        {selected
          .filter(([, row]) => !row.ready)
          .map(([key, row]) => (
            <div className="flex flex-wrap items-center gap-1 text-xs" key={key}>
              <span>
                {moduleLabels[key]}：{row.reasons.join('、')}
              </span>
              <Button onClick={() => host.navigate(row.action)} size="inline" variant="link">
                去完善
              </Button>
            </div>
          ))}
        <p className="text-xs text-muted-foreground">补齐后按下次排期执行，也可手动执行；补资料本身不会发布或发送。</p>
      </div>
    </section>
  )
}
