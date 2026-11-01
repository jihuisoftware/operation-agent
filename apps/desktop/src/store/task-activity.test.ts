import { atom, cleanStores } from 'nanostores'
import { afterEach, expect, it, vi } from 'vitest'

import { createTaskActivity, type TaskActivity, type TaskActivityOwner } from './task-activity'

const stores: ReturnType<typeof createTaskActivity>[] = []
afterEach(() => { cleanStores(...stores); stores.length = 0; vi.useRealTimers() })

it('shares one observer, clears finished/failed executions, and bounds failed refreshes', async () => {
  vi.useFakeTimers()
  const owner = atom<TaskActivityOwner>({ connectionId: 'local', profile: 'default' })
  const load = vi.fn().mockResolvedValue({ running: 2 })
  const activity = createTaskActivity(owner, load)
  stores.push(activity)
  const first = activity.subscribe(() => {})
  const second = activity.subscribe(() => {})
  await vi.advanceTimersByTimeAsync(0)
  expect(load).toHaveBeenCalledTimes(1)
  expect(activity.get().running).toBe(2)
  first()
  load.mockResolvedValue({ running: 0 })
  await vi.advanceTimersByTimeAsync(3000)
  expect(activity.get().running).toBe(0)
  load.mockRejectedValue(new Error('offline'))
  await vi.advanceTimersByTimeAsync(15000)
  expect(load).toHaveBeenCalledTimes(5)
  expect(activity.get()).toEqual({ running: 0, unavailable: true })
  load.mockResolvedValue({ running: 1 })
  window.dispatchEvent(new Event('focus'))
  await vi.advanceTimersByTimeAsync(0)
  expect(activity.get()).toEqual({ running: 1 })
  second()
  await vi.advanceTimersByTimeAsync(1000)
  const calls = load.mock.calls.length
  await vi.advanceTimersByTimeAsync(6000)
  expect(load).toHaveBeenCalledTimes(calls)
})

it('clears on owner switches and ignores late responses from other connections and profiles', async () => {
  vi.useFakeTimers()
  const owner = atom<TaskActivityOwner>({ connectionId: 'local', profile: 'default' })
  const replies: ((value: TaskActivity) => void)[] = []
  const load = vi.fn(() => new Promise<TaskActivity>(resolve => replies.push(resolve)))
  const activity = createTaskActivity(owner, load)
  stores.push(activity)
  const stop = activity.subscribe(() => {})
  await vi.advanceTimersByTimeAsync(6000)
  expect(load).toHaveBeenCalledTimes(1) // Never overlap requests for one owner.
  owner.set({ connectionId: 'remote', profile: 'default' })
  replies[1]!({ running: 1 })
  await vi.advanceTimersByTimeAsync(0)
  expect(activity.get().running).toBe(1)
  owner.set({ connectionId: 'remote', profile: 'work' })
  expect(activity.get().running).toBe(0)
  replies[0]!({ running: 10 })
  await vi.advanceTimersByTimeAsync(0)
  expect(activity.get().running).toBe(0)
  replies[2]!({ running: 3 })
  await vi.advanceTimersByTimeAsync(0)
  expect(activity.get().running).toBe(3)
  expect(load.mock.calls).toEqual([
    [{ connectionId: 'local', profile: 'default' }],
    [{ connectionId: 'remote', profile: 'default' }],
    [{ connectionId: 'remote', profile: 'work' }]
  ])
  stop()
})
