import { useStore } from '@nanostores/react'
import { useCallback, useState } from 'react'

import { $apiRequestScope, hermesApiAs, resolveOwnerNow } from '@/api/client'
import type { CronJob, StatusResponse } from '@/types/hermes'

import { TaskDetails } from '../cron/task-details'
import { useTaskPoll } from '../cron/use-task-poll'

import { AgentProcess } from './agent-process'
import { CronProcess } from './cron-process'

export function ActivityView() {
  const scope = useStore($apiRequestScope)
  const owner = resolveOwnerNow({ ...scope, profile: scope.profile || 'default' })

  return <OwnedActivity key={JSON.stringify(owner)} owner={owner} />
}

function OwnedActivity({ owner: initialOwner }: { owner: ReturnType<typeof resolveOwnerNow> }) {
  const [owner] = useState(initialOwner)

  const load = useCallback(async () => {
    const [status, jobs] = await Promise.all([
      hermesApiAs<StatusResponse>(owner, { path: '/api/status' }),
      hermesApiAs<CronJob[]>(owner, { path: '/api/cron/jobs' })
    ])

    return { status, jobs }
  }, [owner])

  const { data, error } = useTaskPoll(load)
  const running = data?.jobs.filter(job => job.active_execution) || []

  return (
    <section aria-label="实时状态" className="h-full space-y-6 overflow-auto p-5 text-sm">
      <header className="space-y-2"><h1 className="text-xl font-semibold">实时状态</h1>
        <p className="text-muted-foreground">当前连接与 Profile 的运行情况每 3 秒更新；Agent 工具调用随会话事件实时更新。</p>
      </header>
      {error && <p className="select-text text-destructive" role="alert">连接或更新失败，以下为上次收到的数据：{error}</p>}
      {!data && <p>正在读取系统状态…</p>}
      {data && <div className="flex flex-wrap gap-5">
        <span>Server：{data.status.gateway_running ? '运行中' : '未运行'}</span>
        <span>运行中的定时任务：{running.length}</span>
        <span>Profile：{owner.profile}</span>
        <span>最近心跳：{data.status.gateway_updated_at || '暂无'}</span>
        {data.status.gateway_heartbeat_stale_s != null && <span className="text-destructive">心跳延迟 {data.status.gateway_heartbeat_stale_s} 秒</span>}
      </div>}
      <AgentProcess owner={owner} />
      <section aria-label="定时任务执行过程" className="space-y-4">
        <h2 className="font-medium">定时任务执行过程</h2>
        {data && !running.length && <p className="text-muted-foreground">当前没有正在执行的定时任务。</p>}
        {running.map(job => <div className="space-y-2" key={job.id}><h3>{job.name || job.id}</h3>
          <TaskDetails initiallyOpen jobId={job.id} profile={job.profile || owner.profile || 'default'} />
          {!job.no_agent && <CronProcess jobId={job.id} owner={owner} />}
        </div>)}
      </section>
    </section>
  )
}
