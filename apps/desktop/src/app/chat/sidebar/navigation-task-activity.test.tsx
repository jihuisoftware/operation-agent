import { act, cleanup, render, screen } from '@testing-library/react'
import { atom } from 'nanostores'
import { afterEach, expect, it, vi } from 'vitest'

import type { TaskActivity } from '@/store/task-activity'

vi.mock('@/store/navigation-activity', async () => {
  const { atom } = await import('nanostores')

  return { $cronTaskActivity: atom({ running: 0 }), $agentTaskActivity: atom({ running: 0 }) }
})
vi.mock('@/contrib/react/use-contributions', () => ({ useContributions: () => [] }))
vi.mock('@/app/routes', () => ({ SIDEBAR_NAV_AREA: 'sidebar.nav' }))

import { TaskActivityBadge } from './navigation-task-activity'

afterEach(cleanup)

it('shows an accessible animated indicator only for execution, with a static unavailable state', () => {
  const activity = atom<TaskActivity>({ running: 0 })
  render(<TaskActivityBadge activity={activity} label="定时任务" />)
  expect(screen.queryByRole('status')).toBeNull()
  act(() => activity.set({ running: 2 }))
  expect(screen.getByRole('status').getAttribute('aria-label')).toBe('定时任务：2 项任务正在执行')
  act(() => activity.set({ running: 0 }))
  expect(screen.queryByRole('status')).toBeNull()
  act(() => activity.set({ running: 0, unavailable: true }))
  expect(screen.queryByRole('status')).toBeNull()
  expect(screen.getByLabelText(/执行状态暂不可用/)).toBeTruthy()
})
