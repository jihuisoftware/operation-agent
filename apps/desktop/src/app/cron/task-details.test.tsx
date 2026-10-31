import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import type * as ApiClient from '@/api/client'
import { $apiRequestScope, hermesApiAs } from '@/api/client'

import { type TaskDetailData, TaskDetails } from './task-details'

vi.mock('@/api/client', async importOriginal => ({
  ...(await importOriginal<typeof ApiClient>()),
  hermesApiAs: vi.fn()
}))

const data: TaskDetailData = {
  plan: { prompt: '当前任务指令' }, snapshot: { prompt: '执行时指令' }, context: {},
  attempts: [{ id: 'run-one', status: 'running', claimed_at: '2026-10-31T01:00:00Z' }],
  execution: { id: 'run-one', status: 'running', claimed_at: '2026-10-31T01:00:00Z' },
  steps: [{ id: 'research', title: '信息采集', intent: '获取可追溯来源', state: 'running', detail: '正在读取来源', updated: '2026-10-31T01:00:00Z' }],
  events: [], output: null, updated: '2026-10-31T01:00:00Z'
}

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.clearAllMocks()
  $apiRequestScope.set({ connectionId: null, profile: null })
})

it('opens persisted details, polls committed progress and preserves the last result on disconnection', async () => {
  vi.useFakeTimers()
  $apiRequestScope.set({ connectionId: 'remote', profile: 'work' })
  vi.mocked(hermesApiAs).mockResolvedValue(data)
  render(<TaskDetails jobId="one" />)
  expect(hermesApiAs).not.toHaveBeenCalled()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '任务详情与实时进度' })) })
  expect(screen.getByText('正在读取来源')).toBeTruthy()
  expect(hermesApiAs).toHaveBeenLastCalledWith(
    { connectionId: 'remote', profile: 'work' }, { path: '/api/cron/jobs/one/details' })
  vi.mocked(hermesApiAs).mockResolvedValue({ ...data,
    steps: [{ ...data.steps[0], state: 'completed', detail: '已保存 3 条来源' }], output: '完整成果记录' })
  await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
  expect(screen.getByText('已保存 3 条来源')).toBeTruthy()
  expect(screen.getByText('完整成果记录')).toBeTruthy()
  vi.mocked(hermesApiAs).mockRejectedValue(new Error('连接已断开'))
  await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
  expect(screen.getByRole('alert').textContent).toContain('连接已断开')
  expect(screen.getByText('已保存 3 条来源')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '任务详情与实时进度' }))
  const calls = vi.mocked(hermesApiAs).mock.calls.length
  await act(async () => { await vi.advanceTimersByTimeAsync(6000) })
  expect(hermesApiAs).toHaveBeenCalledTimes(calls)
})

it('clears another connection’s detail and ignores its delayed response', async () => {
  $apiRequestScope.set({ connectionId: 'remote-one', profile: 'work' })
  let resolveOld!: (value: TaskDetailData) => void
  vi.mocked(hermesApiAs).mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve }))
  render(<TaskDetails jobId="one" profile="work" />)
  fireEvent.click(screen.getByRole('button', { name: '任务详情与实时进度' }))
  await act(async () => { $apiRequestScope.set({ connectionId: 'remote-two', profile: 'other' }) })
  await act(async () => { resolveOld(data) })
  expect(screen.queryByText('当前任务指令')).toBeNull()
  vi.mocked(hermesApiAs).mockResolvedValue({ ...data, plan: { prompt: '第二个连接的任务' } })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '任务详情与实时进度' })) })
  expect(screen.getByText('第二个连接的任务')).toBeTruthy()
  expect(hermesApiAs).toHaveBeenLastCalledWith(
    { connectionId: 'remote-two', profile: 'work' }, { path: '/api/cron/jobs/one/details' })
})
