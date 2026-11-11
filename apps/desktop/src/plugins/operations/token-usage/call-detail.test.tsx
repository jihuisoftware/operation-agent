import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { CallDetailToggle } from './call-detail'
import { RunCalls } from './run-calls'
import type { CallDetail } from './types'

afterEach(cleanup)

function detail(id: string): CallDetail {
  const call = { id, task_name: '生成图文', stage: 'content', run_id: 'run', purpose: 'content', model: 'test-model', provider: 'test-provider',
    started: 1, received: 3, state: 'confirmed', error_type: '', total_tokens: 37, prompt_tokens: 30, output_tokens: 7,
    cache_read_tokens: 10, cache_write_tokens: 0, reasoning_tokens: 0 }

  return { call, detail: { state: 'completed', request: { messages: [{ role: 'system', content: '完整提示词' }] },
    raw_response: '{"title":"原始标题"}', parsed_result: { title: '原始标题' }, cost: { amount: 0.012, currency: 'USD', source: 'provider_receipt' } },
    attempts: [{ ...call, id: 'first', state: 'failed', model: 'first-model' }, { ...call, id: 'second' }], notice: '' }
}

it('loads only when expanded and opens each retry with its own content and usage', async () => {
  const rest = vi.fn(async (path: string) => detail(path.includes('/first?') ? 'first' : 'second'))
  const ctx = { rest } as unknown as PluginContext
  render(<CallDetailToggle ctx={ctx} identity="second" query="filter_topic=topic&filter_model=test-model" />)
  expect(rest).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: '查看请求详情' }))
  expect(await screen.findByText('费用及来源：0.012 USD · 提供方回执')).toBeTruthy()
  expect(screen.getByText(/完整提示词/)).toBeTruthy()
  expect(screen.getByText(/缓存读取：10/)).toBeTruthy()
  expect(rest).toHaveBeenCalledWith('/usage/calls/second?filter_topic=topic')
  fireEvent.click(screen.getByRole('button', { name: /首次请求/ }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/usage/calls/first?filter_topic=topic'))
  fireEvent.click(screen.getByRole('button', { name: '收起请求详情' }))
  expect(screen.queryByRole('region', { name: '请求详情' })).toBeNull()
})

it('does not show a previous profile response after the owner changes', async () => {
  let resolve!: (value: CallDetail) => void
  const old = { rest: vi.fn(() => new Promise<CallDetail>(done => { resolve = done })) } as unknown as PluginContext
  const next = { rest: vi.fn(async () => ({ ...detail('second'), detail: null, notice: '此请求未保存输入输出，历史原文无法补回。' })) } as unknown as PluginContext
  const view = render(<CallDetailToggle ctx={old} identity="second" />)
  fireEvent.click(screen.getByRole('button', { name: '查看请求详情' }))
  await waitFor(() => expect(old.rest).toHaveBeenCalled())
  view.rerender(<CallDetailToggle ctx={next} identity="second" />)
  await screen.findByText(/历史原文无法补回/)
  resolve(detail('second'))
  await waitFor(() => expect(screen.queryByText(/完整提示词/)).toBeNull())
  expect(screen.getByText('费用及来源：未知（未获得费用回执）')).toBeTruthy()
})

it('opens historical run requests on demand without a current-day filter', async () => {
  const rest = vi.fn(async (path: string) => path.includes('/tasks/') ? { items: [detail('second').call], cursor: null } : detail('second'))
  render(<RunCalls ctx={{ rest } as unknown as PluginContext} run="old-run" />)
  expect(rest).not.toHaveBeenCalled()
  fireEvent.click(screen.getByText('模型调用 · old-run'))
  fireEvent.click(await screen.findByRole('button', { name: '查看请求详情' }))
  await screen.findByText(/费用及来源：0.012/)
  expect(rest).toHaveBeenCalledWith('/usage/tasks/old-run/calls?all_time=1&cursor=')
  expect(rest).toHaveBeenCalledWith('/usage/calls/second?')
})
