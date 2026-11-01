import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { TopicsPanel } from './topics-panel'

afterEach(cleanup)

it('persists a manual topic without starting generation or publication', async () => {
  const data = { version: 7, day: '2026-11-01', scope_topic: '收纳', brief_id: 'brief-1', candidates: [], selected: null as any }

  const rest = vi.fn(async (path: string, options?: any) => {
    if (path === '/topics/select') {
      data.selected = { title: options.body.title, origin: 'manual', source_ids: [], reason: '用户指定' }

      return data.selected
    }

    return { ...data }
  })

  render(<TopicsPanel ctx={{ rest } as unknown as PluginContext} />)
  fireEvent.change(await screen.findByLabelText('手动指定选题'), { target: { value: '300 元厨房收纳改造' } })
  fireEvent.click(screen.getByRole('button', { name: '使用这个选题' }))
  expect(await screen.findByText('用户已指定')).toBeTruthy()
  expect(screen.getByText('300 元厨房收纳改造')).toBeTruthy()
  expect(rest).toHaveBeenCalledWith('/topics/select', { method: 'POST', body: { title: '300 元厨房收纳改造', version: 7 } })
  expect(rest.mock.calls.every(([path]) => ['/topics', '/topics/select'].includes(path))).toBe(true)
})

it('selects a candidate by its saved batch and shows a rejected stale selection', async () => {
  const data = { version: 2, day: '2026-11-01', scope_topic: '收纳', brief_id: 'b1',
    candidates: [{ title: '收纳步骤', reason: '实测资料', source_ids: ['s1'] }], selected: null }

  const rest = vi.fn(async (path: string) => {
    if (path === '/topics/select') { throw new Error('候选选题已变化') }

    return data
  })

  render(<TopicsPanel ctx={{ rest } as unknown as PluginContext} />)
  fireEvent.click(await screen.findByRole('button', { name: '选用' }))
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('候选选题已变化'))
  expect(rest).toHaveBeenCalledWith('/topics/select', { method: 'POST', body: { candidate_index: 0, brief_id: 'b1', version: 2 } })
  expect(screen.queryByText('用户已指定')).toBeNull()
})
