import { useStore } from '@nanostores/react'
import { useCallback, useState } from 'react'

import { $apiRequestScope, hermesApiAs, resolveOwnerNow } from '@/api/client'
import { Button } from '@/components/ui/button'

import { ContributedBlueprints } from '../cron/contributed-blueprints'
import { useTaskPoll } from '../cron/use-task-poll'

interface PlannedJob {
  job_id: string
  name: string
  instant: string
  plan: string
  state: string
  intent: string
  script?: string
  no_agent: boolean
}

export function UpcomingView() {
  const scope = useStore($apiRequestScope)
  const owner = resolveOwnerNow({ ...scope, profile: scope.profile || 'default' })

  return <OwnedUpcoming key={JSON.stringify(owner)} owner={owner} />
}

function OwnedUpcoming({ owner: initialOwner }: { owner: ReturnType<typeof resolveOwnerNow> }) {
  const [owner] = useState(initialOwner)
  const load = useCallback(() => hermesApiAs<{ jobs: PlannedJob[] }>(owner, { path: '/api/cron/upcoming' }), [owner])
  const { data, error, refresh } = useTaskPoll(load)
  const [pending, setPending] = useState<string | null>(null)
  const [actionError, setActionError] = useState('')

  const cancel = async (job: PlannedJob) => {
    setPending(job.job_id); setActionError('')

    try {
      await hermesApiAs(owner, { path: `/api/cron/jobs/${encodeURIComponent(job.job_id)}/cancel-next`, method: 'POST',
        body: { instant: job.instant, plan: job.plan } })
      refresh()
    } catch (reason) { setActionError(String(reason)) } finally { setPending(null) }
  }

  return (
    <section aria-label="待执行任务" className="h-full space-y-6 overflow-auto p-5 text-sm">
      <header className="space-y-2"><h1 className="text-xl font-semibold">待执行任务</h1>
        <p className="text-muted-foreground">按当前 Profile 展示待执行步骤。取消仅影响所选批次或时段，后续排期不变；已经开始的步骤不能从待执行列表取消。</p>
      </header>
      {(error || actionError) && <p className="select-text text-destructive" role="alert">数据更新或操作失败，请重试：{actionError || error}</p>}
      <ContributedBlueprints profile={owner.profile || 'default'} view="upcoming" />
      <h2 className="font-medium">其他定时任务 · 下一次执行</h2>
      {!data && <p>正在读取任务…</p>}
      {data?.jobs.length === 0 && <p className="text-muted-foreground">没有其他待执行任务。</p>}
      {data?.jobs.map(job => (
        <details className="space-y-3" key={`${job.job_id}:${job.instant}`} open>
          <summary className="cursor-pointer font-medium">{job.name} · {new Date(job.instant).toLocaleString()}</summary>
          <p>{job.state === 'cancelled' ? '已取消本次执行' : job.state === 'claimed' ? '已开始执行' : '待执行'}</p>
          <details><summary className="cursor-pointer">执行步骤：{job.no_agent ? '运行脚本' : '执行 Agent 任务'}</summary>
            <pre className="mt-2 select-text whitespace-pre-wrap break-words font-sans">{job.intent}</pre>
            {job.script && !job.no_agent && <p>先执行准备脚本：{job.script}</p>}
            <p className="text-muted-foreground">该任务按一个执行单元调度。Agent 在运行中产生的工具调用将在实时状态中展示。</p>
          </details>
          <Button disabled={pending !== null || job.state !== 'pending'} onClick={() => void cancel(job)} size="sm" variant="outline">
            {pending === job.job_id ? '正在取消…' : '取消本次步骤'}
          </Button>
        </details>
      ))}
    </section>
  )
}
