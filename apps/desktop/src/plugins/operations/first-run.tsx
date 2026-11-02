import { Badge, Button, CopyButton, formatTimestamp, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import { moduleLabels } from './blueprint-types'

interface FirstRun {
  events?: unknown[]
  errors?: unknown[]
  run: { id: string; state: string; detail?: string } | null
  steps: { id: string; stage: string; state: string; detail: string; started: string }[]
}

const states: Record<string, string> = {
  pending: '等待执行',
  running: '执行中',
  completed: '完成',
  partial: '部分完成',
  needs_attention: '待完善',
  failed: '失败',
  skipped: '跳过',
  cancelled: '取消',
  interrupted: '中断'
}

export function FirstRunProgress({ ctx }: { ctx: PluginContext }) {
  const [data, setData] = useState<FirstRun | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let disposed = false
    let busy = false

    const load = async () => {
      if (busy) {
        return
      }

      busy = true

      try {
        const value = await ctx.rest<FirstRun>('/quick-start')

        if (!disposed) {
          setData(value)
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

    void load()
    const timer = setInterval(() => void load(), 3000)

    return () => {
      disposed = true
      clearInterval(timer)
    }
  }, [ctx])

  if (!data?.run) {
    return error ? <p role="alert">首轮状态暂不可用：{error}</p> : null
  }

  return (
    <section aria-label="快速首轮" className="space-y-3 border-t pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-medium">快速首轮</h2>
        <Badge variant="muted">{states[data.run.state] || data.run.state}</Badge>
        <CopyButton label="复制完整过程" showLabel text={JSON.stringify(data, null, 2)} />
        <CopyButton label="只复制错误" showLabel text={JSON.stringify(data.errors || [], null, 2)} />
      </div>
      {error && <p role="alert">{error}</p>}
      {['pending', 'running'].includes(data.run.state) && (
        <Button
          onClick={() =>
            void ctx
              .rest('/quick-start/cancel', { method: 'POST', body: { id: data.run!.id } })
              .catch(reason => setError(String(reason)))
          }
          variant="outline"
        >
          取消首轮后续步骤
        </Button>
      )}
      {!data.steps.length && <p className="text-muted-foreground">等待现有调度器领取任务；Server 需要保持运行。</p>}
      {data.steps.map(step => (
        <details key={step.id}>
          <summary className="cursor-pointer">
            {moduleLabels[step.stage]} · {states[step.state] || step.state} · {formatTimestamp(step.started)}
          </summary>
          <p className="whitespace-pre-wrap py-2 select-text">{step.detail || '正在处理…'}</p>
        </details>
      ))}
      {data.run.detail && (
        <details>
          <summary className="cursor-pointer">首轮结果</summary>
          <pre className="whitespace-pre-wrap break-words text-xs">{data.run.detail}</pre>
        </details>
      )}
    </section>
  )
}
