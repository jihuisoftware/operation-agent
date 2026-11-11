import { host } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { WorkerBoundary } from './worker-boundary'

vi.mock('@hermes/plugin-sdk', async importOriginal => ({
  ...await importOriginal<Record<string, unknown>>(), host: { notify: vi.fn() }
}))
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('isolates a crashed account view and only remounts it after an explicit retry', () => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
  let broken = true
  const AccountView = () => {
    if (broken) { throw new Error('执行器组件错误') }

    return <p>执行器已重新挂载</p>
  }
  render(<><p>其他账号继续运行</p><WorkerBoundary visible><AccountView /></WorkerBoundary></>)
  expect(screen.getByText('其他账号继续运行')).toBeTruthy()
  expect(screen.getByRole('alert').textContent).toContain('已停止接收新任务')
  expect(host.notify).toHaveBeenCalledWith(expect.objectContaining({ kind: 'error' }))
  broken = false
  expect(screen.queryByText('执行器已重新挂载')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '重新连接执行器' }))
  expect(screen.getByText('执行器已重新挂载')).toBeTruthy()
})
