import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, expect, it, vi } from 'vitest'

import { type ModelBudget, ModelBudgetFields } from './model-budget-fields'
import { SharedModelBudget } from './shared-model-budget'

afterEach(cleanup)

it('edits a numeric limit and switches budget modes without losing either value', () => {
  function Harness() {
    const [value, change] = useState<ModelBudget>({ mode: 'calls', calls: 200, tokens: 1_000_000 })

    return <ModelBudgetFields onChange={change} value={value} />
  }

  render(<Harness />)
  fireEvent.change(screen.getByRole('spinbutton', { name: '当前主题每日模型调用上限' }), { target: { value: '250' } })
  fireEvent.change(screen.getByRole('combobox', { name: '当前主题预算方式' }), { target: { value: 'tokens' } })
  fireEvent.change(screen.getByRole('spinbutton', { name: '当前主题每日 Token 上限' }), { target: { value: '50000' } })
  fireEvent.change(screen.getByRole('combobox', { name: '当前主题预算方式' }), { target: { value: 'calls' } })
  expect((screen.getByRole('spinbutton') as HTMLInputElement).value).toBe('250')
  fireEvent.change(screen.getByRole('combobox', { name: '当前主题预算方式' }), { target: { value: 'tokens' } })
  expect((screen.getByRole('spinbutton') as HTMLInputElement).value).toBe('50000')
})

it('saves the shared budget explicitly with its revision and shows usage', async () => {
  const snapshot = { version: 3, config: { mode: 'calls', calls: 200, tokens: 1_000_000 }, day: '2026-11-03', usage: { calls: 17, tokens: 1234, unknown: 1, pending: 0 } }
  const rest = vi.fn(async (_path: string, options?: { method?: string; body: { config: ModelBudget; version: number } }) => options?.method === 'PUT' ? { ...snapshot, version: 4, config: options.body.config } : snapshot)
  const { container } = render(<SharedModelBudget ctx={{ rest } as unknown as PluginContext} />)
  const details = container.querySelector('details')!
  details.open = true
  fireEvent(details, new Event('toggle'))
  const limit = await screen.findByRole('spinbutton', { name: '全部主题共享每日模型调用上限' })
  fireEvent.change(limit, { target: { value: '300' } })
  expect(rest.mock.calls.some(([, options]) => options?.method === 'PUT')).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: '保存共享预算' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/model-budget', { method: 'PUT', body: { version: 3, config: { ...snapshot.config, calls: 300 } } }))
  expect(await screen.findByText('共享模型预算已保存')).toBeTruthy()
  expect(screen.getByText(/正常调用 17 次/)).toBeTruthy()
})
