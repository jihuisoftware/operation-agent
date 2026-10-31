import { afterEach, expect, it, vi } from 'vitest'

import { executeBrowser } from './browser'
import type { Api, BrowserCommand, Guest } from './types'

afterEach(() => vi.useRealTimers())

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

function fixture() {
  let url = 'about:blank'

  const guest = {
    loadURL: vi.fn(async (next: string) => {
      url = next
    }),
    getURL: () => url,
    executeJavaScript: vi.fn(async (code: string) => {
      const request = JSON.parse(code.slice(code.lastIndexOf(')(') + 2, -1))

      if (request.operation === 'account') {
        return { account_id: 'me' }
      }

      if (request.operation === 'post-result') {
        throw new Error('连接中断')
      }

      return { ok: true }
    })
  } as unknown as Guest

  const api = vi.fn(async (path: string) =>
    path === '/policy'
      ? { version: 3, policy: { enabled: true, paused: false, account_id: 'me', topic: '主题' } }
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
    .mock.calls.map(([code]) => JSON.parse(code.slice(code.lastIndexOf(')(') + 2, -1)))

  expect(requests.filter(request => request.operation === 'commit-post')).toHaveLength(1)
})
