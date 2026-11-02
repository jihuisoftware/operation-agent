import { host, type PluginContext } from '@hermes/plugin-sdk'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

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
})

it('shows ledger outcomes, expandable progress and links to the relevant management section', async () => {
  const rest = vi.fn(async (path: string) => (path === '/quick-start' ? { run: null, steps: [] } : data))
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
    path === '/quick-start' ? Promise.resolve({ run: null, steps: [] }) : replies()
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
  expect(rest.mock.calls[1][1]?.owner).toEqual(nextOwner)
})
