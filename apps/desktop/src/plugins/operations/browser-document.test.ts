import { afterEach, expect, it, vi } from 'vitest'

import { pageScript, waitForDocument } from './browser-document'
import { BrowserExecution } from './browser-execution'
import { waitForRead } from './browser-wait'
import type { Guest } from './types'

afterEach(() => vi.useRealTimers())

function fixture() {
  let loading = true

  const guest = { getURL: () => 'https://www.xiaohongshu.com/search_result', isLoadingMainFrame: () => loading,
    remove: vi.fn() } as unknown as Guest

  const execution = new BrowserExecution({ id: 'slow', kind: 'inbox', payload: {}, expires: Date.now() / 1000 + 600 }, guest)

  return { guest, execution, loaded: () => { loading = false } }
}

it('does not charge loading time against content readiness or wrap a composite read in five seconds', async () => {
  vi.useFakeTimers()
  const f = fixture()
  let reads = 0
  setTimeout(f.loaded, 45000)

  const result = waitForRead(async () => {
    await waitForDocument(f.guest, f.execution)
    await f.execution.wait(() => new Promise<void>(resolve => setTimeout(resolve, 3000)), 10000)

    return ++reads === 2
  }, Boolean, 15000, false, undefined, f.execution)

  await vi.advanceTimersByTimeAsync(52000)
  expect(await result).toBe(true)
  expect(reads).toBe(2)
  expect(f.execution.controller.signal.aborted).toBe(false)
})

it('cancels a slow loading page without dispatching a late submit', async () => {
  vi.useFakeTimers()
  const f = fixture()
  const submit = vi.fn(async () => 'submitted')
  const result = pageScript(f.guest, f.execution, submit, '提交', undefined, async () => {}).catch(error => error)
  await vi.advanceTimersByTimeAsync(1000)
  f.execution.abort('用户暂停', 'CONTROL_PAUSED')
  f.loaded()
  await vi.advanceTimersByTimeAsync(1000)
  expect(await result).toMatchObject({ code: 'CONTROL_PAUSED' })
  expect(submit).not.toHaveBeenCalled()
  expect(f.execution.dispatchState).not.toBe('submission_started')
})

it('keeps a separate finite script budget after the network becomes ready', async () => {
  vi.useFakeTimers()
  const f = fixture()
  const script = vi.fn(() => new Promise<never>(() => {}))
  setTimeout(f.loaded, 45000)
  const result = pageScript(f.guest, f.execution, script, '脚本读取').catch(error => error)
  await vi.advanceTimersByTimeAsync(46000)
  expect(script).toHaveBeenCalledOnce()
  expect(f.execution.controller.signal.aborted).toBe(false)
  await vi.advanceTimersByTimeAsync(10000)
  expect(await result).toMatchObject({ code: 'BROWSER_UNAVAILABLE' })
  expect(f.guest.remove).toHaveBeenCalledOnce()
})
