import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import type { TaskDetail } from './task-evidence'
import { DebugTaskPage } from './task-page'

afterEach(cleanup)
const owner = { connectionId: 'local', profile: 'debug-owner' }
const base = '/debug/debug%3Aone/tasks/organize'
const started = '2026-11-05T02:30:00Z'
const catalog = { version: 4, task_details_available: true, policy: { modules: { organize: true } }, tasks: [{ id: 'organize', title: '资料整理', module: 'organize' }] }

function trace(label = '已保存有效结果'): TaskDetail {
  return { run: { id: 'debug:one', title: '资料整理', started, state: 'needs_attention', detail: label }, task: 'organize',
    step: { id: 'organize', title: '资料整理', state: 'needs_attention', detail: label }, attempts: [],
    events: [{ id: 1, at: started, kind: 'organization_format', data: { detail: '关键词已兼容', issues: [] } }], more: false, cursor: 1,
    artifacts: [{ id: 'trace:1', kind: 'model_trace', created: started, state: 'completed' }], actions: [], notes: [], policy: { topic: '工程' },
    model_attempts: [{ id: 'call:1', model: '测试模型', provider: '测试服务', state: 'failed', started: 100, received: 190, error_type: 'APITimeoutError', total_tokens: null }],
    trace_notice: '历史未保存的输入无法补回。' }
}

function props(rest: unknown) {
  return { ctx: { rest } as PluginContext, owner, task: 'organize', runId: 'debug:one', selectRun: vi.fn(), back: vi.fn() }
}

it('shows human guidance, real attempts and lazy artifacts without running tasks on entry', async () => {
  const rest = vi.fn(async (path: string) => {
    if (path === '/debug') { return catalog }

    if (path.endsWith('/runs')) { return { runs: [trace().run], next: null } }

    if (path.includes('/artifacts/')) { return { data: { input: '真实业务输入', result: '有效整理结果' } } }

    return trace()
  })

  render(<DebugTaskPage {...props(rest)} />)
  expect(await screen.findByText('已保存有效结果')).toBeTruthy()
  expect(screen.getByText(/APITimeoutError/)).toBeTruthy()
  expect(screen.getByRole('button', { name: '检查整理资料' })).toBeTruthy()
  expect(rest.mock.calls.some(([path]) => path.includes('/artifacts/'))).toBe(false)
  const summary = screen.getByText(/模型业务输入与输出/)
  fireEvent.click(summary)
  await waitFor(() => expect(rest.mock.calls.some(([path]) => path.includes('/artifacts/'))).toBe(true))
  expect(await screen.findByText(/真实业务输入/)).toBeTruthy()
  expect(rest.mock.calls.every(([path]) => path !== '/debug/run')).toBe(true)
})

it('runs only this task and saves notes separately from execution authority', async () => {
  const value = trace()

  const rest = vi.fn(async (path: string, options?: any) => {
    if (path === '/debug') { return catalog }

    if (path.endsWith('/runs')) { return { runs: [value.run], next: null } }

    if (path.endsWith('/notes')) {
      value.notes = [{ id: 'note', created: started, text: options.body.text }]

      return value.notes[0]
    }

    return value
  })

  const input = props(rest)
  render(<DebugTaskPage {...input} />)
  await screen.findByText('已保存有效结果')
  fireEvent.change(screen.getByLabelText('人工调试备注'), { target: { value: '已核对原文，关键词列表可以使用' } })
  fireEvent.click(screen.getByRole('button', { name: '保存备注' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith(`${base}/notes`, expect.objectContaining({ owner, method: 'POST', body: { text: '已核对原文，关键词列表可以使用', request_id: expect.any(String) } })))
  expect(rest.mock.calls.some(([path]) => path === '/debug/run')).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: '快速实测本任务' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/debug/run', expect.objectContaining({ owner, body: {
    task: 'organize', mode: 'quick', version: 4, request_id: expect.any(String)
  } })))
  expect(input.selectRun).toHaveBeenCalledWith(expect.stringMatching(/^debug:/))
})

it('does not mix a late response from the previously selected batch into the new page', async () => {
  let deliver: (value: TaskDetail) => void = () => undefined
  const delayed = new Promise<TaskDetail>(resolve => { deliver = resolve })

  const rest = vi.fn(async (path: string) => {
    if (path === '/debug') { return catalog }

    if (path.endsWith('/runs')) { return { runs: [], next: null } }

    if (path.includes('debug%3Aone')) { return delayed }

    return { ...trace('新批次结果'), run: { ...trace().run, id: 'debug:two' } }
  })

  const input = props(rest)
  const page = render(<DebugTaskPage {...input} />)
  await waitFor(() => expect(rest).toHaveBeenCalledWith(`${base}?after=0`, expect.anything()))
  page.rerender(<DebugTaskPage {...input} runId="debug:two" />)
  expect(await screen.findByText('新批次结果')).toBeTruthy()
  deliver(trace('旧批次迟到结果'))
  await waitFor(() => expect(screen.queryByText('旧批次迟到结果')).toBeNull())
})
