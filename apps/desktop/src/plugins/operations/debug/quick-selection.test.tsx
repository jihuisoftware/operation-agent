import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { QuickSelection } from './quick-selection'

const tasks = [
  { id: 'research', title: '信息采集', module: 'research' },
  { id: 'content', title: '内容生产', module: 'content' },
  { id: 'publish', title: '图文发布', module: 'publish' },
  { id: 'dm', title: '收到私信处理', module: 'dm' },
  { id: 'report', title: '运营日报', module: 'report' }
]

afterEach(cleanup)

it('starts empty and supports explicit all, internal-only and clear choices without starting work', () => {
  const onRun = vi.fn()
  render(<QuickSelection available busy={false} onRun={onRun} tasks={tasks} />)
  const start = screen.getByRole('button', { name: '执行所选项目（真实执行）' }) as HTMLButtonElement
  expect(start.disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '全选' }))
  expect(screen.getByText('已选 5 项')).toBeTruthy()
  expect(screen.getByText(/所选外部动作将直接与生产交互/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '仅内部' }))
  expect(screen.getByText('已选 3 项')).toBeTruthy()
  expect(screen.getByRole('checkbox', { name: '图文发布' }).getAttribute('aria-checked')).toBe('false')
  expect(screen.queryByText(/所选外部动作将直接与生产交互/)).toBeNull()
  expect(onRun).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('checkbox', { name: '内容生产' }))
  fireEvent.click(start)
  expect(onRun).toHaveBeenCalledWith(['research', 'report'], 'quick')
  fireEvent.click(screen.getByRole('button', { name: '清空' }))
  expect(screen.getByText('已选 0 项')).toBeTruthy()
  expect(start.disabled).toBe(true)
})

it('disables changes and execution while busy and does not remember choices across visits', () => {
  const onRun = vi.fn()
  const view = render(<QuickSelection available busy={false} onRun={onRun} tasks={tasks} />)
  fireEvent.click(screen.getByRole('checkbox', { name: '内容生产' }))
  view.rerender(<QuickSelection available busy onRun={onRun} tasks={tasks} />)
  expect((screen.getByRole('checkbox', { name: '内容生产' }) as HTMLButtonElement).disabled).toBe(true)
  const start = screen.getByRole('button', { name: '执行所选项目（真实执行）' }) as HTMLButtonElement
  expect(start.disabled).toBe(true)
  fireEvent.click(start)
  expect(onRun).not.toHaveBeenCalled()
  view.unmount()
  render(<QuickSelection available busy={false} onRun={onRun} tasks={tasks} />)
  expect(screen.getByText('已选 0 项')).toBeTruthy()
})

it('keeps the same explicit selection when changing from quick to detailed mode', () => {
  const onRun = vi.fn()
  render(<QuickSelection available busy={false} onRun={onRun} tasks={tasks} />)
  expect(screen.getByRole('button', { name: '快速模式' }).getAttribute('aria-pressed')).toBe('true')
  fireEvent.click(screen.getByRole('checkbox', { name: '图文发布' }))
  fireEvent.click(screen.getByRole('button', { name: '详细模式' }))
  fireEvent.click(screen.getByRole('button', { name: '执行所选项目（真实执行）' }))
  expect(onRun).toHaveBeenCalledWith(['publish'], 'normal')
  expect(screen.getAllByRole('button', { name: '执行所选项目（真实执行）' })).toHaveLength(1)
  expect(screen.queryByText(/所选外部动作将直接与生产交互/)).toBeNull()
})
