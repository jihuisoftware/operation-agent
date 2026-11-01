import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { OrganizedLibrary } from './organized-library'

afterEach(cleanup)

function data(title: string) {
  return { topic: '收纳', total: 2, organized: 1, usable: 1, pending: 1, matching: 1, categories: { 方法教程: 1 }, next_cursor: null,
    items: [{ id: 'organized:1', source_id: 's1', title, url: 'https://example.org/source', category: '方法教程', summary: '整理后的摘要', relevant: true,
      facts: ['原文描述的方法'], opinions: ['作者认为更方便'], uncertainties: ['效果未独立验证'], keywords: ['厨房'], source_day: '2026-11-01', created: '2026-11-01T01:10:00Z' }] }
}

it('shows classified evidence and filters without starting work or external actions', async () => {
  const rest = vi.fn(async (_path: string) => data('厨房资料'))
  render(<OrganizedLibrary ctx={{ rest } as unknown as PluginContext} />)
  expect(await screen.findByText('厨房资料')).toBeTruthy()
  expect(screen.getByText('效果未独立验证')).toBeTruthy()
  expect(screen.getByText('作者认为更方便')).toBeTruthy()
  expect(screen.getByRole('button', { name: '复制完整整理记录' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '方法教程 · 1' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/organized-sources?q=&category=%E6%96%B9%E6%B3%95%E6%95%99%E7%A8%8B&cursor=0'))
  fireEvent.change(await screen.findByRole('searchbox'), { target: { value: '厨房' } })
  fireEvent.click(screen.getByRole('button', { name: '搜索' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/organized-sources?q=%E5%8E%A8%E6%88%BF&category=%E6%96%B9%E6%B3%95%E6%95%99%E7%A8%8B&cursor=0'))
  expect(rest.mock.calls.every(call => call.length === 1)).toBe(true)
})

it('discards old profile responses after the owning context changes', async () => {
  let resolve!: (value: ReturnType<typeof data>) => void
  const oldRest = vi.fn(() => new Promise<ReturnType<typeof data>>(done => { resolve = done }))
  const nextRest = vi.fn(async () => data('新 Profile 资料'))
  const view = render(<OrganizedLibrary ctx={{ rest: oldRest } as unknown as PluginContext} />)
  view.rerender(<OrganizedLibrary ctx={{ rest: nextRest } as unknown as PluginContext} />)
  expect(await screen.findByText('新 Profile 资料')).toBeTruthy()
  resolve(data('旧 Profile 私有资料'))
  await waitFor(() => expect(screen.queryByText('旧 Profile 私有资料')).toBeNull())
})
