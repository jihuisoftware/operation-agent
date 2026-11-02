import { Button, type CronBlueprintOwner, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

interface PlannedStep {
  readiness?: { ready: boolean; reasons: string[] }
  day: string
  stage: string
  slot: string
  due: string
  state: string
  title: string
  intent: string
  execution_id: string | null
}
interface UpcomingData {
  version: number
  topic: string
  timezone: string
  paused: boolean
  steps: PlannedStep[]
  manual: PlannedStep[]
}

export function UpcomingOperations({ ctx, owner }: { ctx: PluginContext; owner: CronBlueprintOwner }) {
  const [data, setData] = useState<UpcomingData | null>(null)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [pending, setPending] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let disposed = false
    let busy = false

    const refresh = async () => {
      if (busy || document.visibilityState === 'hidden') {
        return
      }

      busy = true

      try {
        const result = await ctx.rest<UpcomingData>('/upcoming', { owner })

        if (!disposed) {
          setData(result)
          setError('')
        }
      } catch (reason) {
        if (!disposed) {
          setError(String(reason))
        }
      } finally {
        busy = false
      }
    }

    void refresh()

    const timer = window.setInterval(() => {
      void refresh()
    }, 3000)

    document.addEventListener('visibilitychange', refresh)

    return () => {
      disposed = true
      clearInterval(timer)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [ctx, owner, revision])

  const cancel = async (step: PlannedStep) => {
    setPending(`${step.day}:${step.stage}:${step.slot}`)
    setActionError('')

    try {
      await ctx.rest('/upcoming/cancel', { owner, method: 'POST', body: { ...step, version: data?.version } })
      setRevision(value => value + 1)
    } catch (reason) {
      setActionError(String(reason))
    } finally {
      setPending(null)
    }
  }

  return (
    <section aria-label="运营待执行步骤" className="space-y-4">
      <h2 className="font-medium">每日运营 · {data?.topic || '当前运营计划'}</h2>
      <p className="text-xs text-muted-foreground">
        显示今天剩余时段、明天的排期，以及当前手动批次尚未开始的步骤。取消记录保存在数据库中。
      </p>
      {(error || actionError) && (
        <p className="select-text text-destructive" role="alert">
          更新或取消失败：{actionError || error}
        </p>
      )}
      {!data && <p>正在读取运营计划…</p>}
      {data?.paused && <p>计划已暂停；以下步骤在恢复前不会执行。</p>}
      {data && data.steps.length + data.manual.length === 0 && <p>没有待执行的运营步骤。</p>}
      {data &&
        [
          { title: '当前手动批次', steps: data.manual },
          ...Array.from(new Set(data.steps.map(step => step.day))).map(day => ({
            title: `${day} · ${data.timezone}`,
            steps: data.steps.filter(step => step.day === day)
          }))
        ]
          .filter(group => group.steps.length > 0)
          .map(group => (
            <details className="space-y-3" key={group.title} open>
              <summary className="cursor-pointer font-medium">{group.title}</summary>
              {group.steps.map(step => (
                <div className="flex items-start justify-between gap-4" key={`${step.day}:${step.stage}:${step.slot}`}>
                  <details className="min-w-0 flex-1">
                    <summary className="cursor-pointer">
                      {step.execution_id ? '手动执行' : step.slot} · {step.title} ·{' '}
                      {step.state === 'cancelled' ? '已取消' : '待执行'}
                    </summary>
                    <p className="mt-2 select-text">{step.intent}</p>
                    {step.readiness && !step.readiness.ready && (
                      <p className="text-xs text-muted-foreground">待完善：{step.readiness.reasons.join('、')}</p>
                    )}
                  </details>
                  <Button
                    disabled={pending !== null || step.state !== 'pending'}
                    onClick={() => void cancel(step)}
                    size="sm"
                    variant="outline"
                  >
                    {pending === `${step.day}:${step.stage}:${step.slot}` ? '正在取消…' : '取消步骤'}
                  </Button>
                </div>
              ))}
            </details>
          ))}
    </section>
  )
}
