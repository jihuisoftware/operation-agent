import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { CollectionSummary } from './collection-summary'

afterEach(cleanup)

it('shows the observed English query and fetches seven-day outcomes only on demand', async () => {
  const rest = vi.fn().mockResolvedValue({ start: '2026-11-01', end: '2026-11-07', keywords: ['工具调用'],
    relevant: 4, relevant_per_100: 40, new_per_100: 50, attempted: 10, organization_calls: 1, fixed_not_read_today: 0,
    cited_english: 2, cited_unknown_language: 0, legacy_batches: 0 })

  render(<CollectionSummary ctx={{ rest } as unknown as PluginContext} data={{
    started: '2026-11-07T01:00:00Z', state: 'completed', limit: 100, succeeded: 9, new: 5, failed: 1, already_read: 0,
    retried: 0, not_attempted: 0, duplicate_content: 4, search_errors: 0, english_reason: '需要官方资料',
    queries: [{ query: 'tool calling evaluation', keyword: '工具调用', language: 'en' }]
  }} />)
  expect(screen.getByText(/英文 · 工具调用 → tool calling evaluation/)).toBeTruthy()
  expect(rest).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: '查看近七日采集成效' }))
  expect(await screen.findByText(/选题引用英文原文 2 条/)).toBeTruthy()
  expect(rest).toHaveBeenCalledWith('/sources/collection-report')
})
