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
