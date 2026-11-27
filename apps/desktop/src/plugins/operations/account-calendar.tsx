import { Button, Input, formatTimestamp, host, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

interface QueuedDraft {
  content_id: string
  title: string
  topic_id?: string
  business_id?: string
  publish_at: string | null
  detail: string
}
interface Calendar {
  account: string
  timezone: string
  slots: string[]
  limit: number
  shared_limit?: number
  queue?: QueuedDraft[]
  revision: number
}
const path = '/account/publication-calendar'

export function AccountCalendar({ ctx }: { ctx: PluginContext }) {
  const [calendar, setCalendar] = useState<Calendar | null>(null)
  const [times, setTimes] = useState('')
  const [notice, setNotice] = useState('')
  const [pending, setPending] = useState(false)
  useEffect(() => {
    let current = true
    setCalendar(null)
    setNotice('')
    void ctx
      .rest<Calendar>(path)
      .then(value => {
        if (current) {
          setCalendar(value)
          setTimes(value.slots.join('、'))
        }
      })
      .catch(error => {
        if (current) setNotice(String(error))
      })
    return () => {
      current = false
    }
  }, [ctx])
  async function save() {
    if (!calendar) return
    setPending(true)
    try {
      const next = await ctx.rest<Calendar>(path, {
        method: 'PUT',
        body: {
          account: calendar.account,
          revision: calendar.revision,
          timezone: calendar.timezone,
          limit: calendar.limit,
          slots: times.split(/[、，,\s]+/).filter(Boolean)
        }
      })
      setCalendar({ ...next, queue: calendar.queue, shared_limit: calendar.shared_limit })
      setTimes(next.slots.join('、'))
      setNotice('账号发布排期已保存')
    } catch (error) {
      setNotice(String(error))
    } finally {
      setPending(false)
    }
  }
  return (
    <section className="mb-5 space-y-2">
      <h2 className="font-semibold">账号发布排期</h2>
      {calendar && (
        <fieldset disabled={pending} className="grid gap-2 sm:grid-cols-3">
          <label>
            发布时区
            <Input value={calendar.timezone} onChange={e => setCalendar({ ...calendar, timezone: e.target.value })} />
          </label>
          <label>
            每日发布时段
            <Input placeholder="10:00、18:00" value={times} onChange={e => setTimes(e.target.value)} />
          </label>
          <label>
            每日发布上限
            <Input
              type="number"
              min={0}
              max={1000}
              value={calendar.limit}
              onChange={e => setCalendar({ ...calendar, limit: Number(e.target.value) })}
            />
          </label>
          <Button onClick={() => void save()}>保存账号排期</Button>
        </fieldset>
      )}
      {calendar?.shared_limit != null && calendar.limit > calendar.shared_limit &&
        <p role="status">当前共享发布上限为每账号每日 {calendar.shared_limit} 篇。排期同时检查主题和共享额度。</p>}
      {calendar?.queue?.map(draft => (
        <p key={draft.content_id}>
          <Button
            variant="link"
            onClick={() => {
              const params = new URLSearchParams({ tab: 'pending', record: draft.content_id })
              if (draft.business_id && draft.topic_id) {
                params.set('business_id', draft.business_id)
                params.set('topic_id', draft.topic_id)
              }
              host.navigate('/content?' + params)
            }}
          >
            {draft.title || '查看稿件'}
          </Button>
          {draft.publish_at ? formatTimestamp(draft.publish_at) : draft.detail || '等待排期'}
        </p>
      ))}
      {notice && <p role="status">{notice}</p>}
    </section>
  )
}
