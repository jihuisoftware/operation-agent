import type { PluginContext } from '@hermes/plugin-sdk'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { $loginNavigation, $loginRequest, $loginWorker, type PlatformLogins } from './login-state'
import { PlatformLoginsPanel } from './platform-logins'

const owner = { connectionId: 'local', profile: 'one' }

const response: PlatformLogins = {
  worker_online: true,
  platforms: [
    {
      id: 'xiaohongshu',
      name: '小红书',
      url: 'https://www.xiaohongshu.com/explore',
      state: 'logged_in',
      observed_state: 'unknown',
      account_mismatch: true,
      account_id: 'me',
      checked_at: '2026-10-31T01:00:00Z',
      reason: '已确认登录，暂未获得新的明确检查结果'
    }
  ]
}

afterEach(() => {
  cleanup()
  $loginWorker.set(null)
  $loginRequest.set(null)
  $loginNavigation.set(null)
})

it('keeps confirmed login visible alongside an inconclusive check and an account warning', async () => {
  $loginWorker.set({ owner, worker: 'window' })
  const rest = vi.fn(async () => response)
  render(<PlatformLoginsPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  expect(await screen.findByText('已登录')).toBeTruthy()
  expect(screen.getByText('最近检查结果：无法确认')).toBeTruthy()
  expect(screen.getByText('账号与运营规则不匹配')).toBeTruthy()
  expect(screen.getByText('平台登录状态 · 1 个待检查或处理')).toBeTruthy()
  expect(screen.getByText(/上次检查：/)).toBeTruthy()
  expect(rest).toHaveBeenCalledWith('/platforms?worker=window', { owner })
  fireEvent.click(screen.getByRole('button', { name: '小红书检查／登录' }))
  expect($loginRequest.get()).toMatchObject({ owner, platform: 'xiaohongshu', url: response.platforms[0].url })
})

it('does not offer another Profile login or paint a late response from that Profile', async () => {
  $loginWorker.set({ owner, worker: 'window' })
  let resolve!: (value: PlatformLogins) => void

  const rest = vi.fn(async (_path: string, options?: any) =>
    options.owner.profile === 'one'
      ? new Promise<PlatformLogins>(r => {
          resolve = r
        })
      : { worker_online: false, platforms: [] }
  )

  const ctx = { rest } as unknown as PluginContext
  const view = render(<PlatformLoginsPanel ctx={ctx} owner={owner} />)
  await waitFor(() => expect(rest).toHaveBeenCalledOnce())
  view.rerender(<PlatformLoginsPanel ctx={ctx} owner={{ connectionId: 'local', profile: 'two' }} />)
  await act(async () => resolve(response))
  expect(screen.queryByText('小红书')).toBeNull()
  expect(await screen.findByText(/当前 Profile 的桌面执行窗口未连接/)).toBeTruthy()
})
