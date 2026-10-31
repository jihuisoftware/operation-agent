import { useCallback } from 'react'

import { hermesApiAs, type ResolvedOwner } from '@/api/client'
import { toChatMessages } from '@/lib/chat-messages'
import type { SessionInfo, SessionMessagesResponse } from '@/types/hermes'

import { useTaskPoll } from '../cron/use-task-poll'

import { ProcessMessages } from './agent-process'

/** Read the scheduler-owned transcript without resuming a session or changing chat focus. */
export function CronProcess({ jobId, owner }: { jobId: string; owner: ResolvedOwner }) {
  const load = useCallback(async () => {
    const { runs } = await hermesApiAs<{ runs: SessionInfo[] }>(owner, {
      path: `/api/cron/jobs/${encodeURIComponent(jobId)}/runs?limit=20`
    })

    const active = runs.find(run => run.scheduler_owned === true && run.source !== 'cron_output')

    if (!active) {return null}

    const result = await hermesApiAs<SessionMessagesResponse>(owner, {
      path: `/api/sessions/${encodeURIComponent(active.id)}/messages?limit=500&order=latest&inline_images=false`
    })

    return toChatMessages(result.messages).filter(message => !message.hidden)
  }, [jobId, owner])

  const { data, error } = useTaskPoll(load)

  return <div className="space-y-2">
    {error && <p className="text-destructive" role="alert">Agent 过程读取失败，保留上次数据：{error}</p>}
    {data && <details open>
      <summary className="cursor-pointer font-medium">Agent 执行过程 · 最近 500 条已保存记录</summary>
      <ProcessMessages messages={data} />
    </details>}
  </div>
}
