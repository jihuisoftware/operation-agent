import { formatTimestamp, type PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { DebugPanel } from './panel'

const owner = { connectionId: 'local', profile: 'dev' }
const started = '2026-11-01T02:10:34.825964+00:00'
afterEach(cleanup)

it('opens a task subpage even before the task has any execution history', async () => {
  const open = vi.fn()

  const rest = vi.fn(async (_path: string) => ({ version: 1, task_details_available: true, policy: { modules: { organize: true } },
    tasks: [{ id: 'organize', title: '资料整理', module: 'organize' }], runs: [] }))

  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} onOpenTask={open} owner={owner} />)
  fireEvent.click(await screen.findByRole('button', { name: '进入资料整理调试子页面' }))
  expect(open).toHaveBeenCalledWith('organize', undefined)
  expect(rest.mock.calls.every(([path]) => path === '/debug')).toBe(true)
})

it('runs only the selected task and shows its saved full trace with a new ID for each click', async () => {
  const data = { version: 3, policy: { modules: { content: true, report: true } }, tasks: [
    { id: 'content', module: 'content', title: '内容生产' }, { id: 'report', module: 'report', title: '运营日报' }
  ], runs: [] as any[] }

  const rest = vi.fn(async (path: string, options?: any) => {
    if (path === '/debug/run') {
      const run = { id: `debug:${options.body.request_id}`, state: 'completed', title: '内容生产', started, detail: '已保存内容版本', duration_ms: 23 }
      data.runs = [run, ...data.runs]

      return run
    }

    if (path === '/debug') { return { ...data } }

    return { run: data.runs[0], events: [{ id: 1, at: started, kind: 'progress', data: { detail: '完整步骤及输出' } }], actions: [] }
  })

  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  fireEvent.click(await screen.findByRole('button', { name: '详细执行内容生产' }))
  expect(await screen.findByText('已保存内容版本')).toBeTruthy()
  expect(screen.getByText(/完整步骤及输出/)).toBeTruthy()
  expect(screen.getByRole('button', { name: '复制完整记录' })).toBeTruthy()
  expect(screen.getAllByTitle(started)).toHaveLength(2)

  for (const time of screen.getAllByTitle(started)) {
    expect(time.textContent).toBe(formatTimestamp(started))
    expect(time.getAttribute('datetime')).toBe(started)
  }

  await waitFor(() => expect((screen.getByRole('button', { name: '详细执行内容生产' }) as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: '详细执行内容生产' }))
  await waitFor(() => expect(rest.mock.calls.filter(([path]) => path === '/debug/run')).toHaveLength(2))
  const calls = rest.mock.calls.filter(([path]) => path === '/debug/run').map(([, options]) => options)
  expect(calls[0]).toMatchObject({ owner, body: { version: 3, task: 'content', mode: 'normal' } })
  expect(calls[1].body.request_id).not.toBe(calls[0].body.request_id)
})

it('shows how to enable a disabled backend and never invokes a task automatically', async () => {
  const rest = vi.fn(async () => { throw new Error('404 调试功能未开启') })
  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  expect((await screen.findByRole('alert')).textContent).toContain('调试功能未开启')
  expect(screen.getByText(/development.operations_debug/)).toBeTruthy()
  expect(rest.mock.calls.every(args => (args as unknown[])[0] === '/debug')).toBe(true)
})

it('has one batch entry that requires an explicit selection and defaults to quick mode', async () => {
  const rest = vi.fn(async (path: string) => path === '/debug' ? {
    version: 7, policy: { modules: { report: true } }, tasks: [{ id: 'report', module: 'report', title: '运营日报' }],
    runs: [], selective_pipeline_available: true
  } : {})

  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  const button = await screen.findByRole('button', { name: '执行所选项目（真实执行）' })
  expect((button as HTMLButtonElement).disabled).toBe(true)
  expect(screen.queryByRole('button', { name: '开始整链路测试（真实执行）' })).toBeNull()
  expect(rest.mock.calls.some(([path]) => path === '/debug/run')).toBe(false)
  fireEvent.click(screen.getByRole('checkbox', { name: '运营日报' }))
  fireEvent.click(button)
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/debug/run', expect.objectContaining({
    owner, body: { task: 'pipeline', mode: 'quick', tasks: ['report'], version: 7, request_id: expect.any(String) }
  })))
})

it('sends quick mode only after the selected task is explicitly requested', async () => {
  const rest = vi.fn(async (path: string) => path === '/debug' ? {
    version: 7, policy: { modules: { publish: true } },
    tasks: [{ id: 'publish', module: 'publish', title: '图文发布' }], runs: []
  } : {})

  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  const button = await screen.findByRole('button', { name: '快速实测图文发布（真实执行）' })
  expect(rest.mock.calls.some(([path]) => path === '/debug/run')).toBe(false)
  fireEvent.click(button)
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/debug/run', expect.objectContaining({
    owner, body: { task: 'publish', mode: 'quick', external_actions: 'execute_once', version: 7, request_id: expect.any(String) }
  })))
})

it('shows and refreshes each task status without opening a history record', async () => {
  const catalog = {
    version: 1, policy: { modules: { research: true, organize: true, content: true } },
    tasks: [{ id: 'research', module: 'research', title: '信息采集' }, { id: 'organize', module: 'organize', title: '资料整理' }, { id: 'content', module: 'content', title: '内容生产' }],
    runs: [{ id: 'debug:live', state: 'running', title: '整链路测试', started, detail: '执行中' }],
    task_status: {
      research: { run_id: 'debug:live', state: 'completed', detail: '读取完成', duration_ms: 200 },
      organize: { run_id: 'debug:live', state: 'running', detail: '正在整理第 2 批资料', duration_ms: 1200 },
      content: { run_id: 'debug:live', state: 'pending', detail: '等待上游步骤' }
    }
  }

  const rest = vi.fn(async () => ({ ...catalog, task_status: { ...catalog.task_status } }))
  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  const row = await screen.findByRole('group', { name: '资料整理' })
  expect(within(row).getByRole('status').textContent).toContain('正在执行')
  expect(within(row).getByText('正在整理第 2 批资料')).toBeTruthy()
  expect(within(screen.getByRole('group', { name: '内容生产' })).getByRole('status').textContent).toContain('等待执行')
  catalog.task_status.organize = { run_id: 'debug:live', state: 'needs_attention', detail: '模型服务繁忙（503），已保留部分资料', duration_ms: 3200 }
  await waitFor(() => expect(within(row).getByRole('status').textContent).toContain('待检查'), { timeout: 5000 })
  expect(within(row).getByText(/模型服务繁忙/)).toBeTruthy()
  expect(rest.mock.calls.every(args => (args as unknown[])[0] === '/debug')).toBe(true)
})

it('shows a scheduled task occupying execution and disables debug submission', async () => {
  const rest = vi.fn(async () => ({ version: 1, policy: { modules: { research: true } },
    tasks: [{ id: 'research', module: 'research', title: '信息采集' }], runs: [], pipeline_available: true,
    execution: { message: '后台正在执行「信息采集」：正在读取来源正文' } }))

  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  expect(await screen.findByText('后台正在执行「信息采集」：正在读取来源正文')).toBeTruthy()
  expect((screen.getByRole('button', { name: '详细执行信息采集' }) as HTMLButtonElement).disabled).toBe(true)
  expect((screen.getByRole('button', { name: '执行所选项目（真实执行）' }) as HTMLButtonElement).disabled).toBe(true)
  expect(rest.mock.calls.every(args => (args as unknown[])[0] === '/debug')).toBe(true)
})

it('explains a rejected busy request never started instead of asking to verify its result', async () => {
  const rest = vi.fn(async (path: string) => {
    if (path === '/debug/run') { throw new Error('409: {"detail":"已有任务执行中，请等待结束或先处理当前任务"}') }

    return { version: 1, policy: { modules: { research: true } },
      tasks: [{ id: 'research', module: 'research', title: '信息采集' }], runs: [] }
  })

  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  fireEvent.click(await screen.findByRole('button', { name: '详细执行信息采集' }))
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toContain('本次调试未启动')
  expect(alert.textContent).not.toContain('核对结果')
})

it('continues the same paused batch with its revision and explicit quick execution scope', async () => {
  const rest = vi.fn(async (path: string) => path === '/debug' ? {
    version: 7, policy: { modules: {} }, tasks: [], runs: [{ id: 'debug:paused', title: '整链路测试', state: 'paused',
      started, revision: 2, detail: '账号已退出', action_mode: 'execute_once' }]
  } : { run: { id: 'debug:paused', state: 'paused' }, events: [], actions: [] })

  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  const button = await screen.findByRole('button', { name: '继续历史批次未完成项目（真实执行）' })
  expect(rest.mock.calls.some(([path]) => path.endsWith('/resume'))).toBe(false)
  fireEvent.click(button)
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/debug/debug%3Apaused/resume', expect.objectContaining({
    body: { request_id: expect.any(String), expected_revision: 2, external_actions: 'execute_once' }
  })))
})

it('submits only checked quick tasks and authorizes external actions only when selected', async () => {
  const tasks = [{ id: 'research', module: 'research', title: '信息采集' }, { id: 'content', module: 'content', title: '内容生产' },
    { id: 'publish', module: 'publish', title: '图文发布' }]

  const rest = vi.fn(async (_path: string, _options?: { body?: Record<string, unknown> }) => ({ version: 4, policy: { modules: { research: true, content: true, publish: true } },
    tasks, runs: [], pipeline_available: true, selective_pipeline_available: true }))

  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  const content = await screen.findByRole('checkbox', { name: '内容生产' })
  const start = screen.getByRole('button', { name: '执行所选项目（真实执行）' }) as HTMLButtonElement
  expect(start.disabled).toBe(true)
  fireEvent.click(content)
  expect(screen.getByText('已选 1 项')).toBeTruthy()
  fireEvent.click(start)
  await waitFor(() => expect(rest.mock.calls.filter(args => args[0] === '/debug/run')).toHaveLength(1))
  const first = (rest.mock.calls.find(args => args[0] === '/debug/run') as unknown as [string, { body: Record<string, unknown> }])[1].body
  expect(first).toMatchObject({ task: 'pipeline', mode: 'quick', tasks: ['content'], version: 4 })
  expect(first).not.toHaveProperty('external_actions')
  await waitFor(() => expect(start.disabled).toBe(false))
  fireEvent.click(screen.getByRole('checkbox', { name: '图文发布' }))
  fireEvent.click(start)
  await waitFor(() => expect(rest.mock.calls.filter(args => args[0] === '/debug/run')).toHaveLength(2))
  const second = (rest.mock.calls.filter(args => args[0] === '/debug/run')[1] as unknown as [string, { body: Record<string, unknown> }])[1].body
  expect(second).toMatchObject({ tasks: ['content', 'publish'], external_actions: 'execute_once' })
})

it('does not send a selected batch to an older quick-only backend to a backend lacking the capability marker', async () => {
  const rest = vi.fn(async () => ({ version: 1, policy: { modules: { research: true } },
    tasks: [{ id: 'research', module: 'research', title: '信息采集' }], runs: [], pipeline_available: true, selective_quick_available: true }))

  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  const start = await screen.findByRole('button', { name: '执行所选项目（真实执行）' }) as HTMLButtonElement
  expect(start.disabled).toBe(true)
  expect(await screen.findByText(/当前后台尚不支持统一按勾选项目执行/)).toBeTruthy()
  fireEvent.click(start)
  expect(rest.mock.calls.every(args => (args as unknown[])[0] === '/debug')).toBe(true)
})

it('continues the stored selection without borrowing newly checked tasks', async () => {
  const rest = vi.fn(async (path: string) => path === '/debug' ? {
    version: 7, policy: { modules: { research: true, publish: true } }, selective_pipeline_available: true,
    tasks: [{ id: 'research', module: 'research', title: '信息采集' }, { id: 'publish', module: 'publish', title: '图文发布' }],
    runs: [{ id: 'debug:chosen', title: '所选项目实测', state: 'paused', started, revision: 2,
      selected_tasks: ['publish'], detail: '账号已退出', action_mode: 'execute_once' }]
  } : { run: { id: 'debug:chosen', state: 'paused' }, events: [], actions: [] })

  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  fireEvent.click(await screen.findByRole('checkbox', { name: '信息采集' }))
  fireEvent.click(screen.getByRole('button', { name: '继续原批次所选项目（真实执行）' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/debug/debug%3Achosen/resume', expect.objectContaining({
    body: { request_id: expect.any(String), expected_revision: 2, external_actions: 'execute_once' }
  })))
})

it('never drops checked tasks when starting a normal batch', async () => {
  const rest = vi.fn(async (_path: string, _options?: unknown) => ({ version: 7, policy: { modules: { research: true, publish: true } },
    tasks: [{ id: 'research', module: 'research', title: '信息采集' }, { id: 'publish', module: 'publish', title: '图文发布' }],
    runs: [], pipeline_available: true, selective_pipeline_available: true }))

  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  fireEvent.click(await screen.findByRole('checkbox', { name: '图文发布' }))
  fireEvent.click(screen.getByRole('button', { name: '详细模式' }))
  fireEvent.click(screen.getByRole('button', { name: '执行所选项目（真实执行）' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/debug/run', expect.objectContaining({
    body: { task: 'pipeline', mode: 'normal', tasks: ['publish'], version: 7, request_id: expect.any(String) }
  })))
})

it('marks unselected rows instead of displaying their older pending status as current work', async () => {
  const rest = vi.fn(async () => ({ version: 1, policy: { modules: { research: true, publish: true } }, selective_pipeline_available: true,
    tasks: [{ id: 'research', module: 'research', title: '信息采集' }, { id: 'publish', module: 'publish', title: '图文发布' }],
    runs: [{ id: 'debug:current', state: 'running', title: '所选项目', started, detail: '执行中', selected_tasks: ['publish'] }],
    task_status: { research: { run_id: 'debug:old', state: 'pending', detail: '旧批次等待采集' },
      publish: { run_id: 'debug:current', state: 'running', detail: '准备发布' } } }))

  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  const research = await screen.findByRole('group', { name: '信息采集' })
  expect(within(research).getByRole('status').textContent).toContain('本次未选择')
  expect(within(research).queryByText('旧批次等待采集')).toBeNull()
  expect(within(research).queryByRole('button', { name: '查看信息采集调试详情' })).toBeNull()
  expect(within(screen.getByRole('group', { name: '图文发布' })).getByRole('status').textContent).toContain('正在执行')
})

it('runs the read-only browser diagnostic only from its explicit button', async () => {
  const rest = vi.fn(async (path: string) => path === '/debug' ? {
    version: 4, policy: { modules: {} }, tasks: [], runs: [], browser_check_available: true
  } : { state: 'completed', detail: '搜索页读取成功，未提交外部动作' })

  render(<DebugPanel ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  const button = await screen.findByRole('button', { name: '只读检查账号与搜索页' })
  expect(rest.mock.calls).toHaveLength(1)
  fireEvent.click(button)
  expect(await screen.findByText('搜索页读取成功，未提交外部动作')).toBeTruthy()
  expect(rest.mock.calls.some(([path]) => path === '/debug/run')).toBe(false)
})
