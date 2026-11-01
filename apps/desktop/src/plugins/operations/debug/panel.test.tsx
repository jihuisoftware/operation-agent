import { type PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { DebugPanel } from './panel'

const owner = { connectionId: 'local', profile: 'dev' }
afterEach(cleanup)

it('runs only the selected task and shows its saved full trace with a new ID for each click', async () => {
  const data = { version: 3, policy: { modules: { content: true, report: true } }, tasks: [
    { id: 'content', module: 'content', title: '内容生产' }, { id: 'report', module: 'report', title: '运营日报' }
  ], runs: [] as any[] }

  const rest = vi.fn(async (path: string, options?: any) => {
    if (path === '/debug/run') {
      const run = { id: `debug:${options.body.request_id}`, state: 'completed', title: '内容生产', started: '2026-10-31', detail: '已保存内容版本', duration_ms: 23 }
      data.runs = [run, ...data.runs]

      return run
    }

    if (path === '/debug') { return { ...data } }

    return { run: data.runs[0], events: [{ id: 1, at: '2026-10-31', kind: 'progress', data: { detail: '完整步骤及输出' } }], actions: [] }
  })

  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  fireEvent.click(await screen.findByRole('button', { name: '单独执行内容生产' }))
  expect(await screen.findByText('已保存内容版本')).toBeTruthy()
  expect(screen.getByText(/完整步骤及输出/)).toBeTruthy()
  expect(screen.getByRole('button', { name: '复制完整记录' })).toBeTruthy()
  await waitFor(() => expect((screen.getByRole('button', { name: '单独执行内容生产' }) as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: '单独执行内容生产' }))
  await waitFor(() => expect(rest.mock.calls.filter(([path]) => path === '/debug/run')).toHaveLength(2))
  const calls = rest.mock.calls.filter(([path]) => path === '/debug/run').map(([, options]) => options)
  expect(calls[0]).toMatchObject({ owner, body: { version: 3, task: 'content' } })
  expect(calls[1].body.request_id).not.toBe(calls[0].body.request_id)
})

it('shows how to enable a disabled backend and never invokes a task automatically', async () => {
  const rest = vi.fn(async () => { throw new Error('404 调试功能未开启') })
  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  expect((await screen.findByRole('alert')).textContent).toContain('调试功能未开启')
  expect(screen.getByText(/development.operations_debug/)).toBeTruthy()
  expect(rest.mock.calls.every(args => (args as unknown[])[0] === '/debug')).toBe(true)
})
