import { useStore } from '@nanostores/react'
import { useEffect, useState } from 'react'

import { $apiRequestScope, hermesApiAs, resolveOwnerNow } from '@/api/client'
import { Button } from '@/components/ui/button'
import { CopyButton } from '@/components/ui/copy-button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useI18n } from '@/i18n'

interface TaskPlan {
  name?: string
  prompt?: string
  script?: string
  schedule?: unknown
  definition?: {
    topic: string
    goal: string
    timezone: string
    enabled: boolean
    paused: boolean
    steps: Array<{ title: string; intent: string; enabled: boolean; times: string[] }>
  }
}
interface Attempt {
  id: string
  status: string
  claimed_at: string
  started_at?: string | null
  finished_at?: string | null
  error?: string | null
}
interface Step {
  id: string
  title: string
  intent: string
  state: string
  detail: string
  updated: string
}
interface TaskEvent {
  id: number
  step_id: string
  detail: string
  data: Record<string, unknown>
  created: string
}
export interface TaskDetailData {
  plan: TaskPlan
  snapshot: TaskPlan | null
  context: { topic?: string; goal?: string; policy_version?: number }
  attempts: Attempt[]
  execution: Attempt | null
  steps: Step[]
  events: TaskEvent[]
  output: string | null
  updated: string | null
}

export function TaskDetails({ jobId, profile, initiallyOpen = false }: { jobId: string; profile?: string; initiallyOpen?: boolean }) {
  const scope = useStore($apiRequestScope)
  const owner = resolveOwnerNow({ connectionId: scope.connectionId, profile: profile || scope.profile })

  return <OwnedTaskDetails initiallyOpen={initiallyOpen} jobId={jobId} key={`${owner.connectionId}:${owner.profile}:${jobId}`} owner={owner} />
}

function OwnedTaskDetails({ jobId, owner: initialOwner, initiallyOpen }: { jobId: string; owner: ReturnType<typeof resolveOwnerNow>; initiallyOpen: boolean }) {
  const { t } = useI18n()
  const c = t.cron.taskDetails
  const [open, setOpen] = useState(initiallyOpen)
  const [data, setData] = useState<TaskDetailData | null>(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState('latest')
  const [owner] = useState(initialOwner)

  useEffect(() => {
    if (!open) {return}
    let disposed = false
    let busy = false

    const load = async () => {
      if (busy || document.visibilityState === 'hidden') {return}
      busy = true

      try {
        const suffix = selected === 'latest' ? '' : `?execution_id=${encodeURIComponent(selected)}`

        const result = await hermesApiAs<TaskDetailData>(owner, {
          path: `/api/cron/jobs/${encodeURIComponent(jobId)}/details${suffix}`
        })

        if (!disposed) { setData(result); setError('') }
      } catch (reason) {
        if (!disposed) {setError(String(reason))}
      } finally { busy = false }
    }

    void load()
    const timer = window.setInterval(() => { void load() }, 3000)
    document.addEventListener('visibilitychange', load)

    return () => {
      disposed = true
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', load)
    }
  }, [jobId, open, owner, selected])

  const label = (state: string) => c.states[state] || state
  const execution = data?.execution
  const snapshot = data?.snapshot || data?.plan

  return (
    <section className="space-y-3">
      <Button aria-expanded={open} onClick={() => setOpen(value => !value)} variant="outline">
        {c.title}
      </Button>
      {open && (
        <div aria-label={c.title} className="space-y-4 text-xs" role="region">
          <p className="text-muted-foreground">{c.refreshHint}</p>
          {error && <p className="select-text whitespace-pre-wrap text-destructive" role="alert">{c.stale} {error}</p>}
          {!data ? <p>{t.cron.loading}</p> : (
            <>
              <details open>
                <summary className="cursor-pointer font-medium">{c.plan}</summary>
                <pre className="mt-2 select-text whitespace-pre-wrap break-words font-sans">{data.plan.prompt || data.plan.script || data.plan.name}</pre>
                {data.plan.definition && (
                  <div className="mt-2 space-y-2">
                    <p>{data.plan.definition.topic} · {data.plan.definition.goal}</p>
                    <p>{data.plan.definition.timezone} · {label(!data.plan.definition.enabled ? 'disabled' : data.plan.definition.paused ? 'paused' : 'enabled')}</p>
                    {data.plan.definition.steps.map(step => (
                      <details key={step.title}>
                        <summary className="cursor-pointer">{step.title} · {step.enabled ? step.times.join('、') : label('disabled')}</summary>
                        <p className="mt-1">{step.intent}</p>
                      </details>
                    ))}
                  </div>
                )}
              </details>
              <Select onValueChange={value => { setSelected(value); setData(null); setError('') }} value={selected}>
                <SelectTrigger aria-label={c.attempt}><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="latest">{c.latest}</SelectItem>
                  {data.attempts.map(attempt => (
                    <SelectItem key={attempt.id} value={attempt.id}>
                      {new Date(attempt.claimed_at).toLocaleString()} · {label(attempt.status)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {execution ? (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <span>{c.status}：{label(execution.status)}</span>
                    <span>{c.updated}：{data.updated ? new Date(data.updated).toLocaleString() : '—'}</span>
                    <CopyButton showLabel text={JSON.stringify(data, null, 2)} />
                  </div>
                  {execution.error && <p className="select-text whitespace-pre-wrap text-destructive">{execution.error}</p>}
                  <details>
                    <summary className="cursor-pointer font-medium">{c.snapshot}</summary>
                    {!data.snapshot && <p>{c.legacy}</p>}
                    <pre className="mt-2 select-text whitespace-pre-wrap break-words">{JSON.stringify({ ...snapshot, ...data.context }, null, 2)}</pre>
                  </details>
                  {!data.steps.length && <p className="text-muted-foreground">{c.noSteps}</p>}
                  {data.steps.map(step => (
                    <details className="space-y-2" key={`${execution.id}:${step.id}`} open={step.state === 'running' || undefined}>
                      <summary className="cursor-pointer font-medium">{step.title} · {label(step.state)}</summary>
                      <p>{step.intent}</p>
                      <p className="text-muted-foreground">{new Date(step.updated).toLocaleString()}</p>
                      <pre className="select-text whitespace-pre-wrap break-words font-sans">{step.detail}</pre>
                      <div className="max-h-72 space-y-2 overflow-auto">
                        {data.events.filter(event => event.step_id === step.id).map(event => (
                          <div className="select-text" key={event.id}>
                            <p>{new Date(event.created).toLocaleTimeString()} · {event.detail}</p>
                            {Object.keys(event.data).length > 0 && <pre className="whitespace-pre-wrap break-words">{JSON.stringify(event.data, null, 2)}</pre>}
                          </div>
                        ))}
                      </div>
                    </details>
                  ))}
                  <details>
                    <summary className="cursor-pointer font-medium">{c.result}</summary>
                    <pre className="mt-2 max-h-96 select-text overflow-auto whitespace-pre-wrap break-words">{data.output ?? c.noResult}</pre>
                  </details>
                </>
              ) : <p>{t.cron.noRuns}</p>}
            </>
          )}
        </div>
      )}
    </section>
  )
}
