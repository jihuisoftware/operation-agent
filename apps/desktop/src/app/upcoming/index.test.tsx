import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import type * as ApiClient from '@/api/client'
import { $apiRequestScope, hermesApiAs } from '@/api/client'

import { UpcomingView } from './index'

vi.mock('@/api/client', async importOriginal => ({ ...(await importOriginal<typeof ApiClient>()), hermesApiAs: vi.fn() }))
vi.mock('../cron/contributed-blueprints', () => ({ ContributedBlueprints: () => null }))

afterEach(() => { cleanup(); vi.clearAllMocks(); $apiRequestScope.set({ connectionId: null, profile: null }) })

it('cancels one persisted occurrence and resets the page when the owning Profile changes', async () => {
  $apiRequestScope.set({ connectionId: 'remote', profile: 'work' })
  const job = { job_id: 'one', name: '资料整理', instant: '2026-11-01T01:00:00Z', plan: 'snapshot-1', state: 'pending', intent: '读取资料并整理来源', no_agent: false }
  vi.mocked(hermesApiAs).mockResolvedValueOnce({ jobs: [job] }).mockResolvedValueOnce({ state: 'cancelled' })
    .mockResolvedValueOnce({ jobs: [{ ...job, state: 'cancelled' }] })
  render(<UpcomingView />)
  await screen.findByText('读取资料并整理来源')
  fireEvent.click(screen.getByRole('button', { name: '取消本次步骤' }))
  await waitFor(() => expect(hermesApiAs).toHaveBeenCalledWith({ connectionId: 'remote', profile: 'work' }, {
    path: '/api/cron/jobs/one/cancel-next', method: 'POST', body: { instant: job.instant, plan: job.plan }
  }))
  await screen.findByText('已取消本次执行')
  expect((screen.getByRole('button', { name: '取消本次步骤' }) as HTMLButtonElement).disabled).toBe(true)
  vi.mocked(hermesApiAs).mockResolvedValue({ jobs: [] })
  await act(async () => { $apiRequestScope.set({ connectionId: 'remote', profile: 'other' }) })
  expect(screen.queryByText('读取资料并整理来源')).toBeNull()
  await screen.findByText('没有其他待执行任务。')
})
