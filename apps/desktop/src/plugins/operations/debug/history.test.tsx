import { type PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { DebugPanel } from './panel'

afterEach(cleanup)
const owner = { connectionId: 'local', profile: 'work' }
const finished = { id: 'debug:old', title: '已结束批次', state: 'failed', started: '2026-11-08T02:00:00Z', detail: '原始错误' }
const paused = { ...finished, id: 'debug:paused', title: '暂停批次', state: 'paused' }

it('cancels all active batches without clearing their history or starting another run', async () => {
  let cancelled = false

  const rest = vi.fn(async (path: string) => {
    if (path === '/debug/cancel-all') { cancelled = true;

 return { cancelled: 1, detail: '已停止后续步骤' } }

    return { version: 1, cancel_all_available: true, history_clear_available: true, tasks: [], policy: { modules: {} },
      runs: [{ ...paused, state: cancelled ? 'cancelled' : 'paused' }] }
  })

  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  await screen.findByRole('button', { name: /暂停批次/ })
  fireEvent.click(screen.getByRole('button', { name: '取消所有批次' }))
  await screen.findByText('已取消 1 个批次。已停止后续步骤')
  expect(await screen.findByRole('button', { name: /暂停批次 · 已取消/ })).toBeTruthy()
  expect(rest).toHaveBeenCalledWith('/debug/cancel-all', expect.objectContaining({ method: 'POST', owner, body: { request_id: expect.any(String) } }))
  expect(rest.mock.calls.some(([path]) => path === '/debug/history/clear' || path === '/debug/run')).toBe(false)
})

it('loads a batch only when expanded and clears ended history with a single scoped request', async () => {
  let cleared = false

  const rest = vi.fn(async (path: string) => {
    if (path === '/debug/history/clear') { cleared = true;

 return { cleared: 35, retained: 1 } }

    if (path === '/debug') { return { version: 1, history_clear_available: true, tasks: [], policy: { modules: {} }, runs: cleared ? [paused] : [finished, paused] } }

    return { run: finished, events: [], actions: [] }
  })

  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  const button = await screen.findByRole('button', { name: /已结束批次/ })
  expect(button.getAttribute('aria-expanded')).toBe('false')
  expect(rest.mock.calls.every(([path]) => path === '/debug')).toBe(true)
  fireEvent.click(button)
  expect(await screen.findByRole('button', { name: '复制完整记录' })).toBeTruthy()
  fireEvent.click(button)
  expect(button.getAttribute('aria-expanded')).toBe('false')
  expect(screen.queryByRole('button', { name: '复制完整记录' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '一键清除历史记录' }))
  await screen.findByText('已清除 35 条历史记录，保留 1 条未结束记录。')
  await waitFor(() => expect(screen.queryByRole('button', { name: /已结束批次/ })).toBeNull())
  expect(screen.getByRole('button', { name: /暂停批次/ }).getAttribute('aria-expanded')).toBe('false')
  expect(rest).toHaveBeenCalledWith('/debug/history/clear', expect.objectContaining({ method: 'POST', owner, body: {} }))
  expect(rest.mock.calls.filter(([path]) => path === '/debug/history/clear')).toHaveLength(1)
})

it('retains records and shows the error if history clearing fails', async () => {
  const rest = vi.fn(async (path: string) => {
    if (path === '/debug/history/clear') { throw new Error('服务暂时不可用') }

    return { version: 1, history_clear_available: true, tasks: [], policy: { modules: {} }, runs: [finished] }
  })

  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  await screen.findByRole('button', { name: /已结束批次/ })
  fireEvent.click(screen.getByRole('button', { name: '一键清除历史记录' }))
  expect((await screen.findByRole('alert')).textContent).toContain('服务暂时不可用')
  expect(screen.getByRole('button', { name: /已结束批次/ })).toBeTruthy()
})
