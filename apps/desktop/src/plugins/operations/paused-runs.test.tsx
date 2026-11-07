import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { PausedRuns } from './paused-runs'

afterEach(cleanup)

it('only resumes after explicit click and sends the saved revision', async () => {
  const rest = vi.fn(async (path: string) => path === '/runs/paused' ? {
    runs: [{ id: 'manual:paused', revision: 3, day: '2026-11-04', error: '账号已退出' }]
  } : { state: 'completed' })

  render(<PausedRuns ctx={{ rest } as unknown as PluginContext} />)
  const button = await screen.findByRole('button', { name: '检查账号并继续未完成步骤' })
  expect(rest.mock.calls).toHaveLength(1)
  fireEvent.click(button)
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/runs/manual%3Apaused/resume', expect.objectContaining({
    method: 'POST', body: { request_id: expect.any(String), expected_revision: 3 }
  })))
})

it('explains an inherited sleep and disables continuing an obsolete batch', async () => {
  const rest = vi.fn(async () => ({ runs: [{ id: 'old-run', revision: 2, day: '2026-11-06',
    error: '受此前主动评论的阻塞影响，本次尚未执行', cause_run_id: 'source-run', cause_started_at: '2026-11-06T10:29:53Z',
    can_resume: false, resume_reason: '日期或规则已变化，请按当前条件重新发起' }] }))

  render(<PausedRuns ctx={{ rest } as unknown as PluginContext} />)
  expect(await screen.findByText(/本次尚未执行/)).toBeTruthy()
  expect((screen.getByRole('button', { name: '检查账号并继续未完成步骤' }) as HTMLButtonElement).disabled).toBe(true)
  expect(screen.getByRole('button', { name: '查看原始任务' })).toBeTruthy()
  expect(rest).toHaveBeenCalledTimes(1)
})
