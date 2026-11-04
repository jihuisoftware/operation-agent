import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { DebugRecord, type Detail, errorLog } from './records'

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

const detail: Detail = {
  run: { id: 'debug:batch', title: '整链路测试', state: 'failed', started: '2026-11-01T02:10:34Z', detail: '选题失败，日报已保存', steps: [
    { id: 'research', title: '信息采集', state: 'completed', detail: '成功采集' },
    { id: 'topics', title: '选题策划', state: 'failed', detail: '模型连接失败', duration_ms: 123 }
  ] },
  events: [
    { id: 1, at: '2026-11-01T02:10:34Z', kind: 'progress', data: { step_id: 'research', detail: '成功采集' } },
    { id: 2, at: '2026-11-01T02:10:35Z', kind: 'debug_exception', data: { step_id: 'topics', error: '模型连接失败', traceback: 'ValueError: 模型连接失败' } },
    { id: 3, at: '2026-11-01T02:10:36Z', kind: 'progress', data: { data: { result: { state: 'unavailable', url: 'https://example.org' } } } }
  ],
  actions: [{ state: 'confirmed', result: { evidence: '成功回执' } }, { state: 'unknown', result: { error: '提交超时' } }]
}

it('copies the entire batch, only errors, or one step without mixing successful output into error logs', async () => {
  const write = vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText: write } })
  render(<DebugRecord detail={detail} />)
  fireEvent.click(screen.getByRole('button', { name: '复制完整记录' }))
  await waitFor(() => expect(write).toHaveBeenCalledWith(JSON.stringify(detail, null, 2)))
  fireEvent.click(screen.getByRole('button', { name: '仅复制错误日志' }))
  await waitFor(() => expect(write).toHaveBeenCalledTimes(2))
  const errors = JSON.parse(write.mock.calls[1][0])
  expect(errors.steps.map((s: { id: string }) => s.id)).toEqual(['topics'])
  expect(errors.events.map((e: { id: number }) => e.id)).toEqual([2, 3])
  expect(errors.actions).toHaveLength(1)
  expect(write.mock.calls[1][0]).not.toContain('成功采集')
  fireEvent.click(screen.getByRole('button', { name: '复制选题策划日志' }))
  await waitFor(() => expect(write).toHaveBeenCalledTimes(3))
  expect(JSON.parse(write.mock.calls[2][0]).events).toEqual([detail.events[1]])
  fireEvent.click(screen.getByText('完整事件（3）'))
  fireEvent.click(screen.getByText(/debug_exception/, { selector: 'summary' }))
  fireEvent.click(screen.getByRole('button', { name: '复制日志 2' }))
  await waitFor(() => expect(write).toHaveBeenCalledTimes(4))
  expect(JSON.parse(write.mock.calls[3][0]).data.traceback).toBe('ValueError: 模型连接失败')
  vi.unstubAllGlobals()
})

it('does not treat ordinary result text mentioning an error as an actual failure', () => {
  const clean = { run: { ...detail.run, state: 'completed', steps: [] }, events: [
    { id: 1, at: '', kind: 'progress', data: { detail: '讨论如何修复 error，非异常', error: null, result: { state: 'confirmed' } } }
  ], actions: [] }

  expect(errorLog(clean).events).toEqual([])
})


it('includes failed browser steps even when the failure is represented by a code rather than text', () => {
  const run = { ...detail, events: [{ id: 4, at: '', kind: 'browser_step', data: { phase: 'failed', error_code: 'PAGE_RESULT_UNCONFIRMED', evidence_id: 'shot' } }] }
  expect(errorLog(run).events).toEqual(run.events)
})

it('shows the saved explicit selection and keeps the diagnostic separate from business steps', () => {
  render(<DebugRecord detail={{ ...detail, run: { ...detail.run, selected_tasks: ['topics'],
    steps: [detail.run.steps![1]], diagnostic_report: { id: 'diagnostic' } } }} />)
  expect(screen.getByText('本次所选项目（1 项）：选题策划')).toBeTruthy()
  expect(screen.getByText('本批次诊断摘要已保存，不计为所选业务步骤。')).toBeTruthy()
  expect(screen.queryByText(/运营日报/, { selector: 'summary' })).toBeNull()
  expect(errorLog({ ...detail, run: { ...detail.run, selected_tasks: ['topics'] } }).run.selected_tasks).toEqual(['topics'])
})
