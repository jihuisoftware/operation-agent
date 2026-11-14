import { QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { host, type PluginRestOptions, queryClient } from '@hermes/plugin-sdk'
import { afterEach, expect, it, vi } from 'vitest'

import { $boardSlug, bindApi, createTask, patchTask } from './api'
import { ExecutionControls } from './execution'

let dispose: (() => void) | undefined
afterEach(() => {
  cleanup()
  dispose?.()
  queryClient.clear()
  vi.restoreAllMocks()
})

it('manual edits never dispatch; run once and revision-checked enable are distinct actions', async () => {
  vi.spyOn(host, 'notify').mockReturnValue('test-notice')
  let enabled = false
  let revision = 0
  const rest = vi.fn(async (path: string, options?: PluginRestOptions) => {
    if (path === '/boards') {
      return { current: 'default' }
    }
    if (path.startsWith('/board?') || path === '/board') {
      return { latest_event_id: 10 }
    }
    if (path === '/boards/default/execution') {
      if (options?.method === 'PUT') {
        const body = options.body as { enabled: boolean; expected_revision: number }
        expect(body.expected_revision).toBe(revision)
        enabled = body.enabled
        revision += 1
      }
      return { board: 'default', enabled, revision, running: 0, dispatcher_running: true }
    }
    if (path.startsWith('/dispatch')) {
      return { spawned: ['task'] }
    }
    return { task: { id: 'manual' } }
  })
  dispose = bindApi(rest as never, { get: (_key, value) => value, set: vi.fn(), remove: vi.fn() }, () => vi.fn())
  $boardSlug.set('default')
  render(
    <QueryClientProvider client={queryClient}>
      <ExecutionControls />
    </QueryClientProvider>
  )
  await screen.findByText('手动模式 · 自动执行关闭')
  await createTask({ title: '人工管理', status: 'todo' })
  await patchTask('manual', { title: '修改标题' })
  expect(rest.mock.calls.some(([path]) => path.startsWith('/dispatch'))).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: '运行一次' }))
  await waitFor(() =>
    expect(rest).toHaveBeenCalledWith('/dispatch?max=1&board=default', expect.objectContaining({ method: 'POST' }))
  )
  expect(enabled).toBe(false)
  await waitFor(() =>
    expect((screen.getByRole('button', { name: '开启本看板自动执行' }) as HTMLButtonElement).disabled).toBe(false)
  )
  fireEvent.click(screen.getByRole('button', { name: '开启本看板自动执行' }))
  expect(enabled).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: '确认开启' }))
  await screen.findByText('自动执行已开启')
  expect(revision).toBe(1)
  await act(async () => fireEvent.click(screen.getByRole('button', { name: '关闭自动执行' })))
  await screen.findByText('手动模式 · 自动执行关闭')
  expect(revision).toBe(2)
})
