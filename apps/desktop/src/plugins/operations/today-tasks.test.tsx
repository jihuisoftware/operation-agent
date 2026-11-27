import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { TodayTasks } from './today-tasks'
import { AccountCalendar } from './account-calendar'

afterEach(cleanup)

it('shows a manuscript shortfall and continues the displayed policy', async () => {
  const daily = {
    version: 4,
    topic: '工程',
    day: '2026-11-27',
    goal: 2,
    completed: 1,
    window: ['08:00', '22:00'],
    enabled: true,
    open: true,
    can_run: true,
    waiting_topic: true,
    runs: [],
    queue: [],
    reasons: {},
    usage: { source: 5, source_limit: 50, model: 7, model_limit: 200, unit: '次' }
  }
  const rest = vi.fn(async (path: string, _options?: unknown) => (path === '/today' ? daily : {}))
  render(<TodayTasks ctx={{ rest } as unknown as PluginContext} />)
  expect(await screen.findByText(/今日新稿 1\/2 篇/)).toBeTruthy()
  expect(screen.getByText(/等待新选题或资料/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '继续今日任务' }))
  await waitFor(() =>
    expect(rest).toHaveBeenCalledWith(
      '/plan/control',
      expect.objectContaining({ body: { action: 'run', version: 4, request_id: expect.any(String) } })
    )
  )
})

it('saves publication slots for the displayed account and revision', async () => {
  const calendar = { account: 'a', revision: 3, limit: 2, timezone: 'Asia/Shanghai', slots: ['10:00'] }
  const rest = vi.fn(async (_path: string, _options?: unknown) => calendar)
  render(<AccountCalendar ctx={{ rest } as unknown as PluginContext} />)
  fireEvent.change(await screen.findByLabelText('每日发布时段'), { target: { value: '10:00、18:00' } })
  fireEvent.click(screen.getByRole('button', { name: '保存账号排期' }))
  await waitFor(() =>
    expect(rest).toHaveBeenCalledWith('/account/publication-calendar', {
      method: 'PUT',
      body: { ...calendar, slots: ['10:00', '18:00'] }
    })
  )
})
