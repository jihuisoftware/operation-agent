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
