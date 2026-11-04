import { afterEach, expect, it, vi } from 'vitest'

import { BrowserExecution } from './browser-execution'
import { BrowserReadinessError, waitForRead } from './browser-wait'
import type { Guest } from './types'

afterEach(() => vi.useRealTimers())

it('a readiness deadline is not an unresponsive guest and preserves evidence capture', async () => {
  vi.useFakeTimers()
  const guest = { remove: vi.fn() } as unknown as Guest
  const context = new BrowserExecution({ id: 'waiting', kind: 'account', payload: {}, expires: Date.now() / 1000 + 120 }, guest)
  const read = () => new Promise<boolean>(resolve => setTimeout(() => resolve(false), 50))
  const outcome = waitForRead(read, Boolean, 1000, false, undefined, context).catch(error => error)
  await vi.advanceTimersByTimeAsync(2500)
  expect(await outcome).toBeInstanceOf(BrowserReadinessError)
  expect(context.controller.signal.aborted).toBe(false)
  expect(guest.remove).not.toHaveBeenCalled()
})
