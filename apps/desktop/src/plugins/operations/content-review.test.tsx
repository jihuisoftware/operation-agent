import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { ContentReview, GenerateContent } from './content-review'

afterEach(cleanup)

it('approves the displayed version for the account scheduler', async () => {
  const rest = vi.fn().mockResolvedValue({})
  const refresh = vi.fn().mockResolvedValue(undefined)
  render(<ContentReview ctx={{ rest } as unknown as PluginContext} refresh={refresh} row={{ id: 'draft', asset_ids: ['cover'], content_revision: 'digest', policy_version: 4 }} />)
  const button = screen.getByRole('button', { name: '审核通过' })
  expect(screen.queryByLabelText('发布时间')).toBeNull()
  fireEvent.click(button)
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/content/draft/approve', {
    method: 'POST', body: { expected_revision: 0, version: 4, content_revision: 'digest' }
  }))
  expect(refresh).toHaveBeenCalledOnce()
})

it('cancels the exact saved schedule revision', async () => {
  const rest = vi.fn().mockResolvedValue({})
  render(<ContentReview ctx={{ rest } as unknown as PluginContext} refresh={async () => undefined} row={{ id: 'draft',
    release: { state: 'scheduled', revision: 3, publish_at: '2027-01-02T05:30:00Z' } }} />)
  expect(screen.queryByRole('button', { name: '审核通过' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '取消排期' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/content/draft/cancel-schedule', { method: 'POST', body: { expected_revision: 3 } }))
})

it('produces a manuscript without submitting a publication request', async () => {
  const rest = vi.fn(async (path: string) => path === '/policy' ? { version: 7 } : { detail: '已保存待审稿件' })
  render(<GenerateContent ctx={{ rest } as unknown as PluginContext} refresh={async () => undefined} />)
  fireEvent.click(screen.getByRole('button', { name: '生成图文' }))
  expect(await screen.findByText('已保存待审稿件')).toBeTruthy()
  expect(rest.mock.calls.map(([path]) => path)).toEqual(['/policy', '/content/generate'])
})

it('shows the actual visual rejection alongside its summary', () => {
  render(<ContentReview ctx={{} as PluginContext} refresh={async () => undefined} row={{
    id: 'draft', visual_check: { reason: '标题超出版面', issues: ['第1页右侧文字被截断'] }
  }} />)
  fireEvent.click(screen.getByText('查看图片评审详情'))
  expect(screen.getByText('第1页右侧文字被截断')).toBeTruthy()
})

it('shows an approved draft waiting for an account slot', () => {
  render(<ContentReview ctx={{} as PluginContext} refresh={async () => undefined} row={{ id: 'draft',
    release: { state: 'waiting_slot', revision: 3, publish_at: null, detail: '等待设置可用的发布时段或额度' } }} />)
  expect(screen.getByText(/等待账号自动排期/)).toBeTruthy()
  expect(screen.getByText('等待设置可用的发布时段或额度')).toBeTruthy()
  expect(screen.queryByRole('button',{name:'审核通过'})).toBeNull()
})
