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

it('requires login when identity is empty instead of returning an executable account', async () => {
  vi.useFakeTimers()
  const { guest, api } = fixture('', '')
  const result = executeBrowser({ ...command, kind: 'account', payload: { policy_version: 3 } }, guest, api)
  await vi.runAllTimersAsync()
  expect(await result).toMatchObject({ state: 'waiting_login', error: expect.stringContaining('扫码登录') })
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
