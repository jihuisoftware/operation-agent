import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ActionManager } from './management'

afterEach(cleanup)
it('lets an operator reconcile a cancelled publication without implicitly retrying it', async () => {
  const rest = vi.fn(async (path: string) => path.endsWith('/detail') ? { issue: { kind: 'pending', title: '提交结果需核对', help: '核对后填写证据' }, tracking: {}, snapshot: null, manual_history: [] } : { steps: [] })
  const refresh = vi.fn(async () => {})
  render(<ActionManager ctx={{ rest } as unknown as PluginContext} rows={[{ id: 'old', kind: 'publish', state: 'cancelled', version: 1, day: '2026-11-09', result: '{}' }]} refresh={refresh} onError={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('核对证据'), { target: { value: '人工检查平台确认未发布' } })
  fireEvent.click(screen.getByRole('button', { name: '保存人工核对' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/actions/old/resolve', { method: 'POST', body: { state: 'confirmed_not_published', evidence: '人工检查平台确认未发布' } }))
  expect(rest.mock.calls.some(([path]) => path.endsWith('/retry'))).toBe(false)
  expect(refresh).toHaveBeenCalledOnce()
})
