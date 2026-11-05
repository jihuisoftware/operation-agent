import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { ContentReview, GenerateContent } from './content-review'

afterEach(cleanup)

it('approves the displayed version and converts the chosen local time to an absolute instant', async () => {
  const rest = vi.fn().mockResolvedValue({})
  const refresh = vi.fn().mockResolvedValue(undefined)
  render(<ContentReview ctx={{ rest } as unknown as PluginContext} refresh={refresh} row={{ id: 'draft', asset_ids: ['cover'], content_revision: 'digest', policy_version: 4 }} />)
  const button = screen.getByRole('button', { name: '审核通过并定时发布' })
  expect((button as HTMLButtonElement).disabled).toBe(true)
  fireEvent.change(screen.getByLabelText('发布时间'), { target: { value: '2027-01-02T13:30' } })
  fireEvent.click(button)
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/content/draft/approve', {
    method: 'POST', body: { expected_revision: 0, version: 4, content_revision: 'digest', publish_at: new Date('2027-01-02T13:30').toISOString() }
  }))
  expect(refresh).toHaveBeenCalledOnce()
})

it('cancels the exact saved schedule revision', async () => {
  const rest = vi.fn().mockResolvedValue({})
  render(<ContentReview ctx={{ rest } as unknown as PluginContext} refresh={async () => undefined} row={{ id: 'draft',
    release: { state: 'scheduled', revision: 3, publish_at: '2027-01-02T05:30:00Z' } }} />)
  expect(screen.queryByRole('button', { name: '审核通过并定时发布' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '取消排期' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/content/draft/cancel-schedule', { method: 'POST', body: { expected_revision: 3 } }))
})

it('produces a manuscript without submitting a publication request', async () => {
  const rest = vi.fn(async (path: string) => path === '/policy' ? { version: 7 } : { detail: '已保存待审稿件' })
  render(<GenerateContent ctx={{ rest } as unknown as PluginContext} refresh={async () => undefined} />)
  fireEvent.click(screen.getByRole('button', { name: '生成待审图文' }))
  expect(await screen.findByText('已保存待审稿件')).toBeTruthy()
  expect(rest.mock.calls.map(([path]) => path)).toEqual(['/policy', '/content/generate'])
})

it('replaces a cover by creating a new unapproved version', async () => {
  const rest = vi.fn(async () => ({ id: 'new-cover' }))
  render(<ContentReview ctx={{ rest } as unknown as PluginContext} refresh={async () => undefined} row={{
    id: 'draft', title: '标题', body: '正文', source_ids: ['source'], asset_ids: ['old-cover', 'second-image']
  }} />)
  fireEvent.change(screen.getByLabelText(/替换封面/), { target: { files: [new File(['image'], 'cover.png', { type: 'image/png' })] } })
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/records/content', { method: 'POST', body: {
    title: '标题', body: '正文', source_ids: ['source'], asset_ids: ['new-cover', 'second-image']
  } }))
  expect(rest).toHaveBeenCalledTimes(2)
})
