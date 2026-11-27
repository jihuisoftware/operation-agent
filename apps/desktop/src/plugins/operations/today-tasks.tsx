import { Button, formatTimestamp, host, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { moduleLabels } from './blueprint-types'

interface Run {
  stage: string
  slot: string
  state: string
  detail: string
}
interface Daily {
  version: number
  day: string
  topic: string
  goal: number
  completed: number
  window: string[]
  next_poll: string | null
  can_run: boolean
  open: boolean
  enabled: boolean
  waiting_topic: boolean
  runs: Run[]
  reasons: Record<string, string[]>
  usage: { source: number; source_limit: number; model: number; model_limit: number; unit: string }
  queue: { content_id: string; publish_at: string | null; state: string; detail: string }[]
}
const sections = [
  {
    title: '内容生产',
    stages: ['research', 'organize', 'analytics', 'industry', 'topics', 'content'],
    path: '/content?tab=topics'
  },
  { title: '消息处理', stages: ['comments', 'dm', 'follow'], path: '/interactions?tab=messages' },
  { title: '主动评论', stages: ['comments'], path: '/interactions?tab=comment' }
]
const states: Record<string, string> = {
  completed: '已完成',
  running: '执行中',
  skipped: '已跳过',
  failed: '失败',
  paused: '已暂停',
  needs_attention: '待处理',
  cancelled: '已取消',
  interrupted: '已中断'
}

export function TodayTasks({ ctx }: { ctx: PluginContext }) {
  const [data, setData] = useState<Daily | null>(null)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [revision, refresh] = useState(0)
  useEffect(() => {
    let current = true
    const load = () =>
      ctx
        .rest<Daily>('/today')
        .then(d => {
          if (current) {
            setData(d)
            setError('')
          }
        })
        .catch(e => {
          if (current) setError(String(e))
        })
    setData(null)
    void load()
    const timer = setInterval(load, 15000)
    return () => {
      current = false
      clearInterval(timer)
    }
  }, [ctx, revision])
  async function resume() {
    if (!data) return
    setBusy(true)
    try {
      const receipt = await ctx.rest<{ detail?: string }>('/plan/control', {
        method: 'POST',
        body: { action: 'run', version: data.version, request_id: crypto.randomUUID() },
        timeoutMs: 1_800_000
      })
      setNotice(receipt.detail || '已请求继续今日任务')
      refresh(n => n + 1)
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="space-y-5 p-4 text-sm">
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {data && (
        <>
          <header className="space-y-2">
            <h2 className="font-semibold">
              {data.topic} · {data.day}
            </h2>
            <p>
              今日新稿 {data.completed}/{data.goal} 篇 · 运营时段 {data.window.join('–')}
            </p>
            <p>
              采集已用 {data.usage.source}/{data.usage.source_limit} 次 · 模型已用 {data.usage.model}/
              {data.usage.model_limit} {data.usage.unit}
            </p>
            <Button
              disabled={!data.enabled || !data.open || (!data.can_run && data.completed >= data.goal) || busy}
              onClick={() => void resume()}
            >
              {busy
                ? '正在继续'
                : !data.enabled
                  ? '计划已暂停'
                  : !data.open
                    ? '当前在运营时段外'
                    : !data.can_run && data.completed >= data.goal
                      ? '今日目标已完成'
                      : '继续今日任务'}
            </Button>
          </header>
          {sections.map(s => (
            <section key={s.title} className="space-y-1">
              <Button variant="link" onClick={() => host.navigate(s.path)}>
                {s.title}
              </Button>
              {s.title === '消息处理' && data.next_poll && <p>下次收件检查 {formatTimestamp(data.next_poll)}</p>}
              {s.title === '内容生产' && data.completed >= data.goal && <p>今日新稿目标已完成</p>}
              {s.title === '内容生产' && data.waiting_topic && (
                <p>
                  等待新选题或资料，还差 {data.goal - data.completed} 篇{' '}
                  <Button variant="link" onClick={() => host.navigate('/materials?tab=sources')}>
                    查看来源
                  </Button>
                </p>
              )}
              {s.stages.map(stage => {
                const run = data.runs.find(
                  r => r.stage === stage && (r.slot === 'daily:outreach') === (s.title === '主动评论')
                )
                const reason = data.reasons[stage]?.join('、')
                return (
                  (run || reason) && (
                    <p key={stage}>
                      {moduleLabels[stage]} · {reason || (run && (run.detail || states[run.state]))}
                    </p>
                  )
                )
              })}
            </section>
          ))}
          <section>
            <Button variant="link" onClick={() => host.navigate('/accounts')}>
              发布队列与账号排期
            </Button>
            {data.queue.length === 0 && <p>当前没有等待发布的稿件</p>}
            {data.queue.map(r => (
              <p key={r.content_id}>
                <Button
                  variant="link"
                  onClick={() => host.navigate('/content?tab=pending&record=' + encodeURIComponent(r.content_id))}
                >
                  {r.publish_at ? formatTimestamp(r.publish_at) : '等待排期'}
                </Button>{' '}
                {r.detail}
              </p>
            ))}
          </section>
        </>
      )}
    </section>
  )
}
