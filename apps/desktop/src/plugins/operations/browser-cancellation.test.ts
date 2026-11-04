import { afterEach, expect, it, vi } from 'vitest'

import { BrowserExecution } from './browser-execution'
import { navigateGuest } from './browser-navigation'
import type { BrowserCommand, Guest } from './types'

function fixture() {
  const guest = document.createElement('div') as unknown as Guest
  document.body.append(guest)
  guest.getURL = () => 'about:blank'
  let finish!: () => void
  guest.loadURL = vi.fn(() => new Promise<void>(resolve => { finish = resolve }))
  const command = { id: 'cancel', kind: 'inbox', expires: Date.now() / 1000 + 600, payload: {} } as BrowserCommand
  const execution = new BrowserExecution(command, guest)

  return { guest, execution, finish: () => finish() }
}

afterEach(() => { document.body.innerHTML = ''; vi.useRealTimers() })

it('bounds a navigation IPC that never acknowledges and quarantines its guest', async () => {
  vi.useFakeTimers()
  const f = fixture()
  let failure: unknown
  void navigateGuest(f.guest, 'https://www.xiaohongshu.com/explore', undefined, f.execution).catch(error => { failure = error })
  await vi.advanceTimersByTimeAsync(120001)
  expect(failure).toMatchObject({ code: 'BROWSER_UNAVAILABLE' })
  expect(f.guest.isConnected).toBe(false)
  f.finish()
  await vi.advanceTimersByTimeAsync(1)
  expect(() => f.execution.assert()).toThrow()
})

it('fences a late read after logout and preserves submission uncertainty', async () => {
  vi.useFakeTimers()
  const f = fixture()
  let finish!: () => void
  const send = vi.fn()
  const pending = f.execution.wait(() => new Promise<void>(resolve => { finish = resolve }), 5000, true).then(send)
  const rejected = expect(pending).rejects.toMatchObject({ code: 'AUTH_REQUIRED' })
  await vi.advanceTimersByTimeAsync(1)
  f.execution.observe('logged_out', '')
  await rejected
  finish()
  await vi.advanceTimersByTimeAsync(1)
  expect(send).not.toHaveBeenCalled()
  expect(f.execution.failure(f.execution.controller.signal.reason)).toMatchObject({ state: 'blocked', submitted: false, dispatch_state: 'read_only' })
  const next = fixture()
  next.execution.submission()
  next.execution.observe('verification', '')
  expect(next.execution.failure(next.execution.controller.signal.reason)).toMatchObject({ state: 'unknown', submitted: true, dispatch_state: 'submission_started' })
})


it('keeps the original cause time only when cancellation came from a persisted block', () => {
  const inherited = fixture()
  const block = { error_code: 'AUTH_REQUIRED', error: '历史登录失效', cause_at: 1700000000.125 }
  inherited.execution.block(block)
  expect(inherited.execution.failure(inherited.execution.controller.signal.reason)).toMatchObject({ cause_at: block.cause_at })
  const observed = fixture()
  observed.execution.observe('logged_out', '')
  observed.execution.block(block)
  expect(observed.execution.failure(observed.execution.controller.signal.reason)).not.toHaveProperty('cause_at')
})

it('records which nested wait is still pending without exposing URL query values', async () => {
  vi.useFakeTimers()
  const { execution } = fixture()
  execution.page(new URL('https://www.xiaohongshu.com/search_result?keyword=private-query'))

  const pending = execution.wait(() => execution.wait(() => new Promise<never>(() => {}), 15000, false, '后台接口 /policy'),
    5000, false, '只读就绪轮询').catch(error => execution.failure(error))

  await vi.advanceTimersByTimeAsync(5001)
  const result = await pending
  expect(result.wait_diagnostics?.timed_out).toBe('只读就绪轮询')
  expect(result.wait_diagnostics?.pending.map(row => row.label)).toContain('后台接口 /policy')
  expect(result.wait_diagnostics?.page?.path).toBe('/search_result')
  expect(JSON.stringify(result)).not.toContain('private-query')
})
