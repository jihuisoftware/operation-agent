import { cleanStores } from 'nanostores'
import { afterEach, expect, it, vi } from 'vitest'

vi.mock('@/api/client', async () => {
  const { atom } = await import('nanostores')

  return { $apiRequestScope: atom({ connectionId: 'local', profile: 'default' }), hermesApiAs: vi.fn() }
})
vi.mock('./session', async () => {
  const { atom } = await import('nanostores')

  return { $gatewayState: atom('open') }
})
vi.mock('./session-states', async () => {
  const { atom } = await import('nanostores')

  return { $sessionStates: atom({}), knownOwnerForSession: vi.fn() }
})

import { $apiRequestScope, hermesApiAs } from '@/api/client'
import type { ClientSessionState } from '@/app/types'
import type { CronJob } from '@/types/hermes'

import { $agentTaskActivity, $cronTaskActivity } from './navigation-activity'
import { $gatewayState } from './session'
import { $sessionStates, knownOwnerForSession } from './session-states'

afterEach(() => { cleanStores($cronTaskActivity, $agentTaskActivity); vi.useRealTimers() })

it('counts only running cron executions, including a manually started paused job', async () => {
  vi.useFakeTimers()
  vi.mocked(hermesApiAs).mockResolvedValue([
    { id: 'manual', enabled: false, active_execution: { id: 'one', status: 'running' } },
    { id: 'pending', enabled: true, active_execution: { id: 'two', status: 'claimed' } },
    { id: 'unknown', enabled: true, active_execution: { id: 'three', status: 'unknown' } },
    { id: 'scheduled', enabled: true, next_run_at: '2099-01-01' }
  ] satisfies CronJob[])
  const stop = $cronTaskActivity.subscribe(() => {})
  await vi.advanceTimersByTimeAsync(0)
  expect($cronTaskActivity.get().running).toBe(1)
  expect(hermesApiAs).toHaveBeenCalledWith(
    { connectionId: 'local', profile: 'default' },
    expect.objectContaining({ path: '/api/cron/jobs' })
  )
  stop()
})

it('excludes waiting input and other owners, and stops animation when the gateway disconnects', () => {
  vi.mocked(knownOwnerForSession).mockImplementation(id => ({ connectionId: id === 'remote' ? 'remote' : 'local', profile: 'default' }))
  const state = (needsInput = false) => ({ busy: true, needsInput } as ClientSessionState)
  $sessionStates.set({ active: state(), waiting: state(true), remote: state() })
  const stop = $agentTaskActivity.subscribe(() => {})
  expect($agentTaskActivity.get().running).toBe(1)
  $apiRequestScope.set({ connectionId: 'local', profile: 'work' })
  expect($agentTaskActivity.get().running).toBe(0)
  $apiRequestScope.set({ connectionId: 'local', profile: 'default' })
  $gatewayState.set('closed')
  expect($agentTaskActivity.get().running).toBe(0)
  stop()
})
