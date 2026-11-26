import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'

import { AttentionPage } from './attention-page'

afterEach(cleanup)

it('pins failed history to the overview day and shows the full reason', async () => {
  const rest = vi.fn(async () => ({ items: [{ id: 'r', stage: 'content', started: '2026-11-26T08:00:00Z', detail: '来源已撤回' }], total: 1 }))
  render(<MemoryRouter initialEntries={['/cron?tab=history&day=2026-11-26']}>
    <AttentionPage ctx={{ rest } as unknown as PluginContext} kind="failed_today" />
  </MemoryRouter>)
  await screen.findByText('来源已撤回')
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/attention/failed_today?before=0&day=2026-11-26'))
})
