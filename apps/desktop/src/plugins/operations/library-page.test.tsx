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
