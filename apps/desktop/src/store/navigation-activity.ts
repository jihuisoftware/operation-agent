import { computed } from 'nanostores'

import { $apiRequestScope, hermesApiAs } from '@/api/client'
import type { CronJob } from '@/types/hermes'

import { $gatewayState } from './session'
import { $sessionStates, knownOwnerForSession } from './session-states'
import { createTaskActivity, type TaskActivity } from './task-activity'

export const $cronTaskActivity = createTaskActivity($apiRequestScope, async owner => {
  const jobs = await hermesApiAs<CronJob[]>(owner, { path: '/api/cron/jobs', timeoutMs: 10000 })

  return { running: jobs.filter(job => job.active_execution?.status === 'running').length }
})

const $runningAgentCount = computed(
  [$sessionStates, $apiRequestScope, $gatewayState],
  (states, owner, gateway) =>
    gateway === 'open' ? Object.entries(states).filter(([id, state]) => {
      if (!state.busy || state.needsInput) { return false }
      const route = knownOwnerForSession(id)

      if (!route) { return false }

      if (typeof route === 'string') {
        return !owner.connectionId && route === (owner.profile || 'default')
      }

      return route.connectionId === owner.connectionId && (route.profile || 'default') === (owner.profile || 'default')
    }).length : 0
)

export const $agentTaskActivity = computed($runningAgentCount, (running): TaskActivity => ({ running }))
