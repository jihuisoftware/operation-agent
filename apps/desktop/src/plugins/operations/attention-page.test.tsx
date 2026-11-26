import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'

import { AttentionPage } from './attention-page'

afterEach(cleanup)

it('shows the message and removes it from the filtered inbox after marking it handled', async () => {
  let handled = false

  const rest = vi.fn(async (path: string) => {
    if (path === '/attention/inbox/handled') {
      handled = true

      return { state: 'handled' }
    }

    return { items: handled ? [] : [{ id: 'account:dm:a/b', text: '这款还有货吗？', created: '2026-11-26T08:00:00Z' }], total: handled ? 0 : 1, next: null }
  })

  render(<MemoryRouter><AttentionPage ctx={{ rest } as unknown as PluginContext} kind="inbox" /></MemoryRouter>)
  await screen.findByText('这款还有货吗？')
  fireEvent.click(screen.getByRole('button', { name: '标记已处理' }))
  await screen.findByText('当前没有符合条件的记录。')
  expect(rest).toHaveBeenCalledWith('/attention/inbox/handled', { method: 'POST', body: { id: 'account:dm:a/b' } })
})

it('pins failed history to the overview day and shows the full reason', async () => {
  const rest = vi.fn(async () => ({ items: [{ id: 'r', stage: 'content', started: '2026-11-26T08:00:00Z', detail: '来源已撤回' }], total: 1 }))
  render(<MemoryRouter initialEntries={['/cron?tab=history&day=2026-11-26']}>
    <AttentionPage ctx={{ rest } as unknown as PluginContext} kind="failed_today" />
  </MemoryRouter>)
  await screen.findByText('来源已撤回')
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/attention/failed_today?before=0&day=2026-11-26'))
})
