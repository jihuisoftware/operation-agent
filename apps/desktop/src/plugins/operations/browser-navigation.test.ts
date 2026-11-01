import { afterEach, expect, it, vi } from 'vitest'

import { navigateGuest } from './browser-navigation'
import type { Guest } from './types'

afterEach(() => vi.useRealTimers())

it('waits for the loaded page even when the IPC navigation promise resolves immediately', async () => {
  vi.useFakeTimers()
  const events = new EventTarget()
  let url = 'about:blank'

  const guest = Object.assign(events, {
    getURL: () => url,
    loadURL: async () => {
      setTimeout(() => {
        url = 'https://www.xiaohongshu.com/explore'
        events.dispatchEvent(new Event('did-stop-loading'))
      }, 20000)
    }
  }) as unknown as Guest

  const nextStep = vi.fn()
  const navigation = navigateGuest(guest, 'https://www.xiaohongshu.com/explore').then(nextStep)
  await vi.advanceTimersByTimeAsync(10000)
  expect(nextStep).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(10000)
  await navigation
  expect(nextStep).toHaveBeenCalledOnce()
})
