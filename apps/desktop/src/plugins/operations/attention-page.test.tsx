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

it('opens the scoped origin without changing the action or sending a request', async () => {
  const {host} = await import('@hermes/plugin-sdk')
  const navigate = vi.spyOn(host,'navigate').mockImplementation(() => {})
  const rest = vi.fn(async () => ({total:1,next:null,items:[{
    id:'f-action',kind:'follow',created:'2026-11-26T08:00:00Z',state:'unknown',target_name:'粉丝',
    evidence:'平台未返回确认',origin:{tab:'messages',source:'follow',record:'msg',business_id:'b',topic_id:'t'}
  }]}))
  try {
    render(<MemoryRouter initialEntries={['/cron?tab=history&historyView=operations.unverified']}>
      <AttentionPage ctx={{rest} as unknown as PluginContext} kind="unverified"/></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button',{name:'查看原记录'}))
    expect(navigate).toHaveBeenCalledWith('/interactions?tab=messages&source=follow&record=msg&business_id=b&topic_id=t')
    expect(rest.mock.calls).toHaveLength(1)
  } finally { navigate.mockRestore() }
})
