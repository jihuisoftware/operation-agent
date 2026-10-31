import type { PluginContext } from '@hermes/plugin-sdk'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { UpcomingOperations } from './upcoming'

const owner = { connectionId: 'remote-work', profile: 'work' }
const step = { day: '2026-11-01', stage: 'publish', slot: '10:00', due: '2026-11-01T10:00:00+08:00', state: 'pending', title: '图文发布', intent: '核对账号和素材后发布', execution_id: null }
const data = { version: 3, topic: '个人成长', timezone: 'Asia/Shanghai', paused: false, steps: [step], manual: [] }

afterEach(() => { cleanup(); vi.useRealTimers(); vi.clearAllMocks() })

it('shows steps and persists cancellation against the exact owner, slot and rule version', async () => {
  const rest = vi.fn().mockResolvedValueOnce(data).mockResolvedValueOnce({ state: 'cancelled' })
    .mockResolvedValue({ ...data, steps: [{ ...step, state: 'cancelled' }] })

  render(<UpcomingOperations ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  await screen.findByText(/10:00 · 图文发布/)
  expect(screen.getByText('核对账号和素材后发布')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '取消步骤' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/upcoming/cancel', {
    owner, method: 'POST', body: { ...step, version: 3 }
  }))
  await screen.findByText(/10:00 · 图文发布 · 已取消/)
  expect((screen.getByRole('button', { name: '取消步骤' }) as HTMLButtonElement).disabled).toBe(true)
})

it('retains a pending step with an actionable error when it already started on the server', async () => {
  const rest = vi.fn().mockResolvedValueOnce(data).mockRejectedValueOnce(new Error('步骤已经开始'))
  render(<UpcomingOperations ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  await screen.findByText(/10:00 · 图文发布/)
  fireEvent.click(screen.getByRole('button', { name: '取消步骤' }))
  expect((await screen.findByRole('alert')).textContent).toContain('步骤已经开始')
  expect(screen.queryByText(/图文发布 · 已取消/)).toBeNull()
})

it('ignores a delayed response from a replaced owner', async () => {
  let resolveOld!: (value: unknown) => void

  const rest = vi.fn().mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve }))
    .mockResolvedValue({ ...data, topic: '其他 Profile', steps: [] })

  const ctx = { rest } as unknown as PluginContext
  const view = render(<UpcomingOperations ctx={ctx} key="old" owner={owner} />)
  view.rerender(<UpcomingOperations ctx={ctx} key="other" owner={{ ...owner, profile: 'other' }} />)
  await screen.findByText('每日运营 · 其他 Profile')
  await act(async () => { resolveOld(data) })
  expect(screen.queryByText(/10:00 · 图文发布/)).toBeNull()
})
