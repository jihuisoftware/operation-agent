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

it('accepts the destination DOM without waiting for hanging loadURL or subresources', async () => {
  vi.useFakeTimers()
  const events = new EventTarget()
  let url = 'https://www.xiaohongshu.com/explore'
  const target = 'https://www.xiaohongshu.com/search_result?keyword=Agent'

  const guest = Object.assign(events, {
    getURL: () => url,
    loadURL: () => {
      setTimeout(() => { url = target; events.dispatchEvent(new Event('dom-ready')) }, 100)

      return new Promise<void>(() => {})
    }
  }) as unknown as Guest

  const finished = vi.fn()
  const pending = navigateGuest(guest, target).then(finished)
  await vi.advanceTimersByTimeAsync(500)
  expect(finished).toHaveBeenCalledOnce()
  await pending
})

it('accepts a ready SPA destination but ignores an unrelated document event', async () => {
  vi.useFakeTimers()
  const events = new EventTarget()
  let url = 'https://www.xiaohongshu.com/explore'
  const target = 'https://www.xiaohongshu.com/search_result?keyword=Agent'
  const guest = Object.assign(events, { getURL: () => url, loadURL: async () => {} }) as unknown as Guest
  const finished = vi.fn()
  const pending = navigateGuest(guest, target).then(finished)
  url = 'https://www.xiaohongshu.com/search_result?keyword=Other'
  events.dispatchEvent(new Event('dom-ready'))
  await vi.advanceTimersByTimeAsync(500)
  expect(finished).not.toHaveBeenCalled()
  url = target + '&source=web'
  events.dispatchEvent(new Event('did-navigate-in-page'))
  await vi.advanceTimersByTimeAsync(500)
  expect(finished).toHaveBeenCalledOnce()
  await pending
})

it('does not confuse DOM readiness with script availability on a still loading URL', async () => {
  vi.useFakeTimers()
  const events = new EventTarget()
  const url = 'https://www.xiaohongshu.com/explore'
  let loading = true

  const guest = Object.assign(events, {
    getURL: () => url,
    isLoadingMainFrame: () => loading,
    executeJavaScript: () => new Promise(() => {}),
    loadURL: vi.fn(async () => {})
  }) as unknown as Guest

  const finished = vi.fn()
  const pending = navigateGuest(guest, url).then(finished)
  await vi.advanceTimersByTimeAsync(500)
  expect(finished).not.toHaveBeenCalled()
  events.dispatchEvent(new Event('dom-ready'))
  await vi.advanceTimersByTimeAsync(500)
  expect(finished).not.toHaveBeenCalled()
  loading = false
  events.dispatchEvent(new Event('did-stop-loading'))
  await vi.advanceTimersByTimeAsync(500)
  await pending
  expect(finished).toHaveBeenCalledOnce()
  expect(guest.loadURL).not.toHaveBeenCalled()
})

it('allows a same-origin login redirect to be inspected instead of waiting for a false timeout', async () => {
  vi.useFakeTimers()
  const events = new EventTarget()
  let url = 'https://www.xiaohongshu.com/explore'

  const guest = Object.assign(events, {
    getURL: () => url,
    loadURL: async () => {
      url = 'https://www.xiaohongshu.com/login'
      events.dispatchEvent(new Event('dom-ready'))
    }
  }) as unknown as Guest

  const pending = navigateGuest(guest, 'https://www.xiaohongshu.com/search_result?keyword=Agent')
  await vi.advanceTimersByTimeAsync(500)
  await pending
})
