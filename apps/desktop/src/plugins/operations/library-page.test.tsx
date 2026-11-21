import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { LibraryPage } from './library-page'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

it('copies the complete daily report markdown', async () => {
  const markdown = '# 今日运营日报\n\n- 已完成选题'
  const write = vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText: write } })
  const rest = vi.fn(async () => ({ report: [{ id: 'report-1', day: '2026-11-01', created: '2026-11-01T02:10:34+00:00', markdown }], actions: [] }))

  render(<LibraryPage ctx={{ rest } as unknown as PluginContext} section="reports" />)

  const copy = await screen.findByRole('button', { name: '复制日报' })
  fireEvent.click(copy)
  await waitFor(() => expect(write).toHaveBeenCalledWith(markdown))
})

it('loads immutable full details only on request and copies the summary separately', async () => {
  const markdown = '# 简明日报\n已完成 5 项'
  const full = '# 完整依据\n原始模型用量回执'
  const write = vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText: write } })

  const rest = vi.fn(async (path: string) => path.includes('/details') ? { markdown: full } : {
    report: [{ id: 'report:2026-11-04', day: '2026-11-04', details_id: 'detail', created: '2026-11-04T02:10:34+00:00', markdown }], actions: []
  })

  render(<LibraryPage ctx={{ rest } as unknown as PluginContext} section="reports" />)
  const button = await screen.findByRole('button', { name: '查看完整详情' })
  expect(rest.mock.calls.some(([path]) => path.includes('/details'))).toBe(false)
  fireEvent.click(button)
  expect(await screen.findByText(/原始模型用量回执/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '复制完整详情' }))
  await waitFor(() => expect(write).toHaveBeenCalledWith(full))
  fireEvent.click(screen.getByRole('button', { name: '复制日报' }))
  await waitFor(() => expect(write).toHaveBeenCalledWith(markdown))
})

it('shows generated covers only after selecting the cover filter', async () => {
  const rest = vi.fn(async (path: string) => {
    if (path.startsWith('/library/assets')) {
      const covers = new URL(path, 'http://local').searchParams.get('filter') === 'covers'
      return { asset: [{ id: 'item', name: covers ? '候选封面.png' : '照片.png' }], actions: [] }
    }
    if (path === '/evidence-storage') {
      return { settings: { days: 30, automatic: false }, categories: [], database_bytes: 0, reusable_bytes: 0 }
    }
    return { data: 'image' }
  })
  render(<LibraryPage ctx={{ rest } as unknown as PluginContext} section="assets" />)
  await screen.findByText('照片.png')
  expect(screen.queryByText('候选封面.png')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '生成的封面图' }))
  await screen.findByText('候选封面.png')
  expect(screen.queryByText('照片.png')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '普通图片' }))
  await screen.findByText('照片.png')
})
