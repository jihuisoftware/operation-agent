import { host, type PluginContext } from '@hermes/plugin-sdk'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { $loginRequest, $loginStatusRevision, $loginWorker, $loginWorkers, loginOwnerKey } from './login-state'
import { OwnedOverview } from './overview'
import type { OverviewData } from './overview-data'

const owner = { connectionId: 'local', profile: 'work' }

const data: OverviewData = {
  day: '2026-11-01',
  timezone: 'Asia/Shanghai',
  updated_at: '2026-11-01T02:00:00+00:00',
  version: 2,
  topic: '个人运营',
  goal: '积累可信资料',
  enabled: true,
  paused: false,
  online: true,
  counts: { sources: 126, sources_read: 125, content: 1, topics: 3, published: 0, interactions: 0, model_calls: 1 },
  pending: { unverified: 1, failed_today: 0, inbox: 0, content: 1 },
  runs: [
    {
      id: 'r',
      stage: 'research',
      state: 'completed',
      detail: '新增 126 条来源',
      started: '2026-11-01T01:00:00+00:00',
      ended: null
    }
  ],
  publications: [],
  report: null,
  schedule: [],
  platforms: []
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  $loginRequest.set(null)
  $loginStatusRevision.set(0)
  $loginWorker.set(null)
  $loginWorkers.set({})
})

it('shows ledger outcomes, expandable progress and links to the relevant management section', async () => {
  const rest = vi.fn(async (path: string) => {
    if (path === '/quick-start') {
      return { run: null, steps: [] }
    }

    if (path.startsWith('/usage/summary?')) {
      return { totals: {}, groups: { topic: [] }, trend: [], until: 0 }
    }

    return data
  })

  const navigate = vi.spyOn(host, 'navigate').mockImplementation(() => {})
  render(<OwnedOverview ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  expect(await screen.findByText('个人运营')).toBeTruthy()
  expect(screen.getByText('126')).toBeTruthy()
  expect(screen.getByText(/结果未知的提交不计入成果/)).toBeTruthy()
  expect(screen.getByText('新增 126 条来源').closest('details')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '查看候选选题' }))
  expect(navigate).toHaveBeenCalledWith('/content?tab=topics')
  expect(rest).toHaveBeenCalledWith('/overview', expect.objectContaining({ owner }))
  expect(rest.mock.calls.filter(([path]) => path === '/overview')).toHaveLength(1)
})

it('ignores a late response from a departed Profile and keeps a visible stale-data error on refresh failure', async () => {
  let resolveOld!: (value: OverviewData) => void

  const replies = vi
    .fn()
    .mockImplementationOnce(
      () =>
        new Promise<OverviewData>(resolve => {
          resolveOld = resolve
        })
    )
    .mockResolvedValueOnce({ ...data, topic: '另一份配置' })
    .mockRejectedValueOnce(new Error('暂时离线'))

  const rest = vi.fn((path: string, _options?: { owner?: unknown }) =>
    path === '/quick-start'
      ? Promise.resolve({ run: null, steps: [] })
      : path === '/workspaces/summary'
        ? Promise.resolve({ items: [] })
        : path.startsWith('/usage/summary?')
          ? Promise.resolve({ totals: {}, groups: { topic: [] }, trend: [], until: 0 })
          : replies()
  )

  const ctx = { rest } as unknown as PluginContext
  const view = render(<OwnedOverview ctx={ctx} key="old" owner={owner} />)
  const nextOwner = { ...owner, profile: 'other' }
  view.rerender(<OwnedOverview ctx={ctx} key="other" owner={nextOwner} />)
  expect(await screen.findByText('另一份配置')).toBeTruthy()
  await act(async () => resolveOld(data))
  expect(screen.queryByText('个人运营')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '刷新' }))
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('暂时离线'))
  expect(screen.getByText('另一份配置')).toBeTruthy()
  expect(rest.mock.calls.filter(([path]) => path === '/overview')[1][1]?.owner).toEqual(nextOwner)
})

it('offers platform reauthorization directly from the overview', async () => {
  const platform = {
    id: 'xiaohongshu',
    name: '小红书',
    url: 'https://www.xiaohongshu.com/explore',
    state: 'logged_out' as const,
    observed_state: null,
    checked_at: null,
    account_id: '',
    reason: '页面明确要求重新登录，请处理后再执行任务。'
  }

  let overview: OverviewData = { ...data, platforms: [platform], platform_worker_online: true }
  $loginWorkers.set({ [loginOwnerKey(owner)]: 'window' })

  const rest = vi.fn(async (path: string) => {
    if (path === '/quick-start') { return { run: null, steps: [] } }

    if (path === '/workspaces/summary') { return { items: [] } }

    if (path.startsWith('/usage/summary?')) { return { totals: {}, groups: { topic: [] }, trend: [], until: 0 } }

    return overview
  })

  render(<OwnedOverview ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  fireEvent.click(await screen.findByRole('button', { name: '小红书重新授权' }))
  expect($loginRequest.get()).toMatchObject({ owner, platform: 'xiaohongshu', url: platform.url })
  overview = { ...overview, platforms: [{ ...platform, state: 'logged_in', account_id: 'me' }] }
  await act(async () => { $loginStatusRevision.set($loginStatusRevision.get() + 1) })
  expect(await screen.findByText('已登录')).toBeTruthy()
  expect(screen.queryByText('已退出或过期')).toBeNull()
})
