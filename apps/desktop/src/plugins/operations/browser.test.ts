import { afterEach, expect, it, vi } from 'vitest'

import { executeBrowser } from './browser'
import type { Api, BrowserCommand, Guest } from './types'

afterEach(() => vi.useRealTimers())

function requestFromScript(code: string) {
  const expression = code.slice(0, code.lastIndexOf('; } catch'))

  const argumentsSource = expression.slice(expression.lastIndexOf(')(') + 2, -1)

  return new Function(`return [${argumentsSource}][0]`)()
}

const command: BrowserCommand = {
  id: 'job',
  kind: 'publish',
  expires: Date.now() / 1000 + 120,
  payload: {
    policy_version: 3,
    account_id: 'me',
    content: { title: '标题', body: '内容', asset_ids: ['image'] }
  }
}

function fixture(account = 'me', configured = 'me') {
  let url = 'about:blank'
  const events = new EventTarget()

  const guest = {
    addEventListener: events.addEventListener.bind(events),
    removeEventListener: events.removeEventListener.bind(events),
    loadURL: vi.fn(async (next: string) => {
      url = next
      events.dispatchEvent(new Event('did-stop-loading'))
    }),
    getURL: () => url,
    executeJavaScript: vi.fn(async (code: string) => {
      const request = requestFromScript(code)

      if (request === 'xiaohongshu') {
        return { state: account ? 'logged_in' : 'unknown', account_id: account }
      }

      if (request.operation === 'notes') { return { ready: true, notes: [] } }

      if (request.operation === 'post-result') {
        throw new Error('连接中断')
      }

      return { ok: true, ready: true }
    })
  } as unknown as Guest

  const api = vi.fn(async (path: string) =>
    path === '/policy'
      ? { version: 3, policy: { enabled: true, paused: false, account_id: configured, topic: '主题' } }
      : { name: 'image.png', data: '' }
  )

  return { guest, api: api as unknown as Api }
}

it('refuses commands from an older policy without navigating', async () => {
  const { guest, api } = fixture()
  expect(
    await executeBrowser({ ...command, payload: { ...command.payload, policy_version: 2 } }, guest, api)
  ).toMatchObject({ state: 'blocked' })
  expect(guest.loadURL).not.toHaveBeenCalled()
})

it('records uncertainty after submission and never retries the publishing click', async () => {
  vi.useFakeTimers()
  const { guest, api } = fixture()
  const result = executeBrowser(command, guest, api)
  await vi.runAllTimersAsync()
  expect(await result).toMatchObject({ state: 'unknown', error: '连接中断' })

  const requests = vi
    .mocked(guest.executeJavaScript)
    .mock.calls.map(([code]) => requestFromScript(code))

  expect(requests.filter(request => request.operation === 'commit-post')).toHaveLength(1)
})


it.each(['first', 'second'])('resolves the live login %s without a configured account or external action', async account => {
  vi.useFakeTimers()
  const { guest, api } = fixture(account, '')
  const result = executeBrowser({ ...command, kind: 'account', payload: { policy_version: 3 } }, guest, api)
  await vi.runAllTimersAsync()
  expect(await result).toMatchObject({ account_id: account })
  expect(guest.executeJavaScript).toHaveBeenCalledTimes(1)
})

it('keeps an unconfirmed identity blocked without claiming that the account logged out', async () => {
  vi.useFakeTimers()
  const { guest, api } = fixture('', '')
  const result = executeBrowser({ ...command, kind: 'account', payload: { policy_version: 3 } }, guest, api)
  await vi.runAllTimersAsync()
  expect(await result).toMatchObject({ state: 'blocked', submitted: false, error_code: 'BROWSER_UNAVAILABLE', error: expect.stringContaining('登录状态仍未确认') })
})

it.each(['me', 'another'])('checks the captured action account against live login %s in automatic mode', async account => {
  vi.useFakeTimers()
  const { guest, api } = fixture(account, '')
  const result = executeBrowser(command, guest, api)
  await vi.runAllTimersAsync()
  expect(await result).toMatchObject(account === 'me'
    ? { state: 'unknown', error: '连接中断' }
    : { state: 'blocked', error: expect.stringContaining('当前登录账号不匹配') })

  const requests = vi.mocked(guest.executeJavaScript).mock.calls
    .map(([code]) => requestFromScript(code))

  expect(requests.filter(request => request.operation === 'commit-post')).toHaveLength(account === 'me' ? 1 : 0)
})


it.each([{ keywords: [] }, { keywords: ['   '] }])('uses the operating topic when keywords are empty: %j', async ({ keywords }) => {
  const { guest, api } = fixture()
  await executeBrowser({ ...command, kind: 'inbox', payload: { policy_version: 3, account_id: 'me', kind: 'comment', keywords } }, guest, api)
  expect(guest.loadURL).toHaveBeenCalledWith('https://www.xiaohongshu.com/search_result?keyword=' + encodeURIComponent('主题'))
})

it('reports a readiness timeout as unsubmitted and recoverable without clicking send', async () => {
  vi.useFakeTimers()
  const { guest, api } = fixture('me')
  vi.mocked(guest.executeJavaScript).mockImplementation(async code => {
    const request = requestFromScript(code)

    return request === 'xiaohongshu' ? { state: 'logged_in', account_id: 'me' } : { ready: false, reason: '未取得列表内容' }
  })
  const pending = executeBrowser({ ...command, kind: 'inbox', payload: { policy_version: 3, account_id: 'me', kind: 'reply' } }, guest, api)
  await vi.runAllTimersAsync()
  expect(await pending).toMatchObject({ state: 'blocked', submitted: false, error_code: 'PAGE_NOT_READY' })
  expect(vi.mocked(guest.executeJavaScript).mock.calls.some(([code]) => requestFromScript(code).operation === 'commit-interaction')).toBe(false)
})


it('stops before preparing or submitting when navigation reveals an expired login', async () => {
  const { guest, api } = fixture()
  vi.mocked(guest.executeJavaScript).mockImplementation(async code => {
    const request = requestFromScript(code)

    if (request === 'xiaohongshu') {
      return guest.getURL().includes('/notification') ? { state: 'logged_out', account_id: '' } : { state: 'logged_in', account_id: 'me' }
    }

    return { ready: true, ok: true }
  })
  const result = await executeBrowser({ ...command, kind: 'interact', payload: { policy_version: 3, account_id: 'me', kind: 'reply' } }, guest, api)
  expect(result).toMatchObject({ state: 'blocked', submitted: false, error_code: 'AUTH_REQUIRED', dispatch_state: 'read_only' })
  expect(vi.mocked(guest.executeJavaScript).mock.calls.some(([code]) => requestFromScript(code).operation === 'commit-interaction')).toBe(false)
})

it('keeps a hung submission unknown and never dispatches its click twice', async () => {
  vi.useFakeTimers()
  const { guest, api } = fixture()
  vi.mocked(guest.executeJavaScript).mockImplementation(async code => {
    const request = requestFromScript(code)

    if (request === 'xiaohongshu') { return { state: 'logged_in', account_id: 'me' } }

    if (request.operation === 'notes') { return { ready: true, notes: [] } }

    if (request.operation === 'commit-post') { return new Promise(() => {}) }

    return { ok: true, ready: true }
  })
  const pending = executeBrowser(command, guest, api)
  await vi.runAllTimersAsync()
  expect(await pending).toMatchObject({ state: 'unknown', submitted: true, dispatch_state: 'submission_started', error_code: 'BROWSER_UNAVAILABLE' })
  expect(vi.mocked(guest.executeJavaScript).mock.calls.filter(([code]) => requestFromScript(code).operation === 'commit-post')).toHaveLength(1)
})


it('waits for a transient logged-out page to settle before deciding the account probe failed', async () => {
  vi.useFakeTimers()
  const { guest, api } = fixture()
  const restored = Date.now() + 2700
  vi.mocked(guest.executeJavaScript).mockImplementation(async () => Date.now() < restored
    ? { state: 'logged_out', account_id: '' } : { state: 'logged_in', account_id: 'me' })
  const pending = executeBrowser({ ...command, kind: 'account', payload: { policy_version: 3 } }, guest, api)
  await vi.runAllTimersAsync()
  expect(await pending).toMatchObject({ state: 'logged_in', account_id: 'me' })
})


it('does not submit while a navigation login signal is being confirmed, then proceeds after cookie recovery', async () => {
  vi.useFakeTimers()
  const { guest, api } = fixture()
  const restored = Date.now() + 2700
  vi.mocked(guest.executeJavaScript).mockImplementation(async code => {
    const request = requestFromScript(code)

    if (request === 'xiaohongshu') {
      return guest.getURL().includes('/notification') && Date.now() < restored
        ? { state: 'logged_out', account_id: '' } : { state: 'logged_in', account_id: 'me' }
    }

    return request.operation === 'interaction-result' ? { state: 'confirmed', evidence: '模拟确认' } : { ready: true, ok: true }
  })
  const pending = executeBrowser({ ...command, kind: 'interact', payload: { policy_version: 3, account_id: 'me', kind: 'reply' } }, guest, api)
  const submits = () => vi.mocked(guest.executeJavaScript).mock.calls.filter(([code]) => requestFromScript(code).operation === 'commit-interaction')
  await vi.advanceTimersByTimeAsync(2500)
  expect(submits()).toHaveLength(0)
  await vi.advanceTimersByTimeAsync(1000)
  expect(await pending).toMatchObject({ state: 'confirmed' })
  expect(submits()).toHaveLength(1)
})

it('reads search candidates through the diagnostic account command without submitting', async () => {
  vi.useFakeTimers()
  const { guest, api } = fixture()

  const result = executeBrowser({ ...command, kind: 'account', payload: { policy_version: 3,
    resume_probe: true, readonly_inventory: 'comment', keywords: ['主题'] } }, guest, api)

  await vi.runAllTimersAsync()
  expect(await result).toMatchObject({ state: 'logged_in', probe: 'account_and_search' })
  const operations = vi.mocked(guest.executeJavaScript).mock.calls.map(([script]) => requestFromScript(script)?.operation)
  expect(operations).toContain('inventory')
  expect(operations).not.toContain('commit-post')
  expect(operations).not.toContain('commit-interaction')
})
