import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { TokenSavingSettings } from './token-saving-settings'

const mocks = vi.hoisted(() => ({
  data: {} as Record<string, unknown>,
  scope: { connectionId: 'local', profile: 'one' },
  save: vi.fn(),
  invalidate: vi.fn()
}))

vi.mock('@/hermes', () => ({ saveHermesConfig: (...args: unknown[]) => mocks.save(...args) }))
vi.mock('../hooks/use-config-record', () => ({
  useHermesConfigRecord: () => ({ data: mocks.data, writeScope: mocks.scope }),
  invalidateHermesConfig: (...args: unknown[]) => mocks.invalidate(...args)
}))
beforeEach(() => {
  mocks.data = { other_setting: 'preserved' }
  mocks.scope = { connectionId: 'local', profile: 'one' }
  mocks.save.mockImplementation(async patch => {
    mocks.data = { ...mocks.data, ...patch }
  })
})
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

it('defaults to normal behavior and saves independent parsing controls only to their owner', async () => {
  render(<TokenSavingSettings profile="one" />)
  expect(screen.getByRole('switch', { name: '解析图像' }).getAttribute('aria-checked')).toBe('true')
  fireEvent.click(screen.getByRole('switch', { name: '启用节省 Token 模式' }))
  expect(screen.getByRole('switch', { name: '解析图像' }).getAttribute('aria-checked')).toBe('false')
  expect(screen.getByRole('switch', { name: '解析文件' }).getAttribute('aria-checked')).toBe('false')
  fireEvent.click(screen.getByRole('switch', { name: '解析图像' }))
  fireEvent.click(screen.getByRole('button', { name: '保存节省设置' }))
  await screen.findByText('已保存，下次新输入及解析调用生效。')
  expect(mocks.save).toHaveBeenCalledWith(
    { token_saving: { enabled: true, parse_images: true, parse_files: false } },
    { connectionId: 'local', profile: 'one' }
  )
  expect(mocks.data.other_setting).toBe('preserved')
  expect(mocks.invalidate).toHaveBeenCalledWith({ connectionId: 'local', profile: 'one' })
})

it('keeps edits on failure and drops an old owner draft and late save message on Profile switch', async () => {
  mocks.save.mockRejectedValueOnce(new Error('offline'))
  const view = render(<TokenSavingSettings profile="one" />)
  fireEvent.click(screen.getByRole('switch', { name: '启用节省 Token 模式' }))
  fireEvent.click(screen.getByRole('button', { name: '保存节省设置' }))
  await screen.findByText(/保存失败.*offline/)
  expect(screen.getByRole('switch', { name: '启用节省 Token 模式' }).getAttribute('aria-checked')).toBe('true')
  let complete!: () => void
  mocks.save.mockImplementationOnce(
    () =>
      new Promise<void>(resolve => {
        complete = resolve
      })
  )
  fireEvent.click(screen.getByRole('button', { name: '保存节省设置' }))
  await waitFor(() => expect(mocks.save).toHaveBeenCalledTimes(2))
  mocks.scope = { connectionId: 'other', profile: 'two' }
  view.rerender(<TokenSavingSettings profile="two" />)
  expect(screen.getByRole('switch', { name: '启用节省 Token 模式' }).getAttribute('aria-checked')).toBe('false')
  await act(async () => complete())
  expect(screen.queryByText(/已保存/)).toBeNull()
})
