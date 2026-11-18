import { type PluginContext } from '@hermes/plugin-sdk'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ReviewPolicySettings, ContentReviewDecision } from './review-policy'

afterEach(cleanup)
it('keeps manual as the server default and saves a score threshold with its own revision', async () => {
  const rest = vi.fn(async (_path: string, options?: { method: string }) => ({
    mode: options?.method === 'PUT' ? 'score' : 'manual',
    threshold: 85,
    revision: options?.method === 'PUT' ? 1 : 0
  }))
  render(<ReviewPolicySettings ctx={{ rest } as unknown as PluginContext} />)
  const mode = (await screen.findByLabelText('审核模式')) as HTMLSelectElement
  expect(mode.value).toBe('manual')
  fireEvent.change(mode, { target: { value: 'score' } })
  fireEvent.click(screen.getByText('保存审核策略'))
  await waitFor(() =>
    expect(rest).toHaveBeenCalledWith('/review-policy', {
      method: 'PUT',
      body: { mode: 'score', threshold: 85, expected_revision: 0 }
    })
  )
  expect(rest.mock.calls.some(([path]) => path.includes('publish'))).toBe(false)
})
it('ignores an old topic settings reply after switching scope', async () => {
  let resolve!: (value: unknown) => void
  const old = {
    rest: vi.fn(
      () =>
        new Promise(r => {
          resolve = r
        })
    )
  } as unknown as PluginContext
  const current = {
    rest: vi.fn(async () => ({ mode: 'manual', threshold: 90, revision: 4 }))
  } as unknown as PluginContext
  const view = render(<ReviewPolicySettings ctx={old} />)
  view.rerender(<ReviewPolicySettings ctx={current} />)
  await screen.findByLabelText('审核模式')
  await act(async () => resolve({ mode: 'automatic', threshold: 85, revision: 1 }))
  expect((screen.getByLabelText('审核模式') as HTMLSelectElement).value).toBe('manual')
})
it('manual writing does not expose automatic recheck and scores remain separate', () => {
  render(
    <ContentReviewDecision
      ctx={{ rest: vi.fn() } as unknown as PluginContext}
      refresh={vi.fn()}
      row={{
        manual: true,
        automatic_review: { approved: false, reason: '等待人工审核', threshold: 85, scores: { text: 99, visual: 70 } }
      }}
    />
  )
  expect(screen.queryByText('重新检查并应用当前策略')).toBeNull()
  expect(screen.getByText(/正文评分：99.*图片评分：70/)).toBeTruthy()
})
