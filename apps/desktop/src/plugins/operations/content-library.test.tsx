import type { PluginContext } from '@hermes/plugin-sdk'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { ContentLibrary } from './content-library'
import { ContentEditor } from './management'

afterEach(() => { cleanup(); vi.useRealTimers() })
const counts = { drafts: 1, pending: 0, published: 0 }
const content = { id: 'one', title: '待审稿件', excerpt: '列表摘要', created: '2026-11-08T02:00:00Z', asset_ids: [] }

it('loads summaries first, fetches full evidence only when opened, and leaves idle lists unpolled', async () => {
  const rest = vi.fn(async (path: string) => path.startsWith('/library/')
    ? { compact: true, content: [content], actions: [], counts, has_active: false }
    : { content: { ...content, body: '完整正文只在展开后读取', source_ids: [], policy_version: 1, content_revision: 'fp' }, assets: [], sources: [] })

  render(<ContentLibrary ctx={{ rest } as unknown as PluginContext} tab="drafts" />)
  await screen.findByText('列表摘要')
  expect(rest.mock.calls.every(([path]) => path.startsWith('/library/'))).toBe(true)
  vi.useFakeTimers()
  await act(async () => { await vi.advanceTimersByTimeAsync(60000) })
  expect(rest).toHaveBeenCalledTimes(1)
  vi.useRealTimers()
  fireEvent.click(screen.getByRole('button', { name: '预览与审核' }))
  expect(await screen.findByText('完整正文只在展开后读取')).toBeTruthy()
  expect(rest).toHaveBeenCalledWith('/content/one/details')
})

it('sends the publication-state filter to the server rather than hiding rows after paging', async () => {
  const rest = vi.fn(async () => ({ compact: true, content: [], actions: [], counts, has_active: false }))
  render(<ContentLibrary ctx={{ rest } as unknown as PluginContext} tab="published" />)
  await screen.findByText('当前筛选下暂无发布记录。')
  expect(screen.queryByRole('button', { name: '生成待审图文' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '失败 / 取消' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith(expect.stringContaining('status=failed')))
})

it('edits a failed publication as a source-bound new version without rewriting the old manuscript', async () => {
  const rest = vi.fn(async () => ({ id: 'new-version' }))
  render(<ContentEditor assets={[]} ctx={{ rest } as unknown as PluginContext} onError={vi.fn()} refresh={async () => {}} rows={[{ id: 'old', title: '原稿', body: '原正文', source_ids: ['source'], asset_ids: ['cover'],
      policy_version: 3, content_revision: 'original-fingerprint', publication_state: 'failed', analysis_context: { private: 'server-owned' } }]}
    sources={[]} />)
  fireEvent.change(screen.getByLabelText('内容正文'), { target: { value: '修改后的正文' } })
  fireEvent.click(screen.getByRole('button', { name: '保存待审核版本' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/content/old/versions', { method: 'POST', body: {
    title: '原稿', body: '修改后的正文', source_ids: ['source'], asset_ids: ['cover'], version: 3,
    content_revision: 'original-fingerprint', request_id: expect.any(String), cancel_original_schedule: false
  } }))
})

it('keeps manual writing available when the review queue is empty', async () => {
  const rest = vi.fn(async (path: string) => path === '/content/editor-options' ? { sources: [], assets: [] }
    : { compact: true, content: [], actions: [], counts, has_active: false })

  render(<ContentLibrary ctx={{ rest } as unknown as PluginContext} tab="drafts" />)
  await screen.findByText('暂无待审核稿件，可以生成图文或选择其他分类。')
  fireEvent.click(screen.getByRole('button', { name: '手动写稿' }))
  expect(await screen.findByLabelText('内容标题')).toBeTruthy()
  expect(rest).toHaveBeenCalledWith('/content/editor-options')
})

it.each([false, true])('distinguishes platform publication from incomplete content checks, historical=%s', async historical => {
  const rest = vi.fn(async () => ({ compact: true, actions: [{ ...content, publication_state: 'submitted',
    publication: { platform: 'published' }, verification_stale: historical }], counts, has_active: false }))

  render(<ContentLibrary ctx={{ rest } as unknown as PluginContext} tab="published" />)
  expect(await screen.findByText(historical ? '此前确认发布 · 待复核' : '平台已发布 · 内容待核对')).toBeTruthy()
})

it('releases the deep-link record when filtering and can reload the same filter twice', async () => {
  const rest = vi.fn(async (path: string) => {
    if (!path.startsWith('/library/')) { return { content: { ...content, id: 'draft', publication_state: 'published' }, sources: [], assets: [] } }
    const linked = new URLSearchParams(path.split('?')[1]).get('record')

    return { compact: true, actions: [{ ...content, id: linked || 'failed', title: linked ? '指定稿件' : '失败稿件', publication_state: linked ? 'published' : 'failed' }], counts, has_active: false }
  })

  render(<ContentLibrary ctx={{ rest } as unknown as PluginContext} record="specific" tab="published" />)
  await screen.findByRole('button', { name: '查看全部记录' })
  const filter = screen.getByRole('button', { name: '失败 / 取消' })
  fireEvent.click(filter)
  await screen.findByText('失败稿件')
  const queries = () => rest.mock.calls.filter(([path]) => path.startsWith('/library/'))
  const previous = queries().length
  expect(new URLSearchParams(queries().at(-1)![0].split('?')[1]).get('record')).toBe('')
  fireEvent.click(filter)
  await waitFor(() => expect(queries().length).toBeGreaterThan(previous))
  expect(await screen.findByText('失败稿件')).toBeTruthy()
})
