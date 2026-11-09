import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeAll, expect, it, vi } from 'vitest'

import { CollectionSettings } from './collection-settings'
import { SourceLimitField } from './source-limit-field'

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false
  Element.prototype.setPointerCapture ??= () => undefined
  Element.prototype.releasePointerCapture ??= () => undefined
  Element.prototype.scrollIntoView ??= () => undefined
})
afterEach(cleanup)
const snapshot = { version: 4, limit: 10000, used: 180, day: '2026-11-09', shared_limit: 10000, shared_used: 180, shared_day: '2026-11-09', remaining: 9820 }

it('offers bounded presets and saves only the chosen topic allowance after an explicit click', async () => {
  const rest = vi.fn(async (_path: string, options?: { method?: string; body?: { limit: number } }) => options?.method === 'PUT' ? { ...snapshot, version: 5, limit: options.body!.limit, remaining: 320 } : snapshot)
  render(<CollectionSettings ctx={{ rest } as unknown as PluginContext} />)
  await screen.findByRole('combobox', { name: '采集每日上限' })
  expect(rest).toHaveBeenCalledOnce()
  fireEvent.keyDown(screen.getByRole('combobox', { name: '采集每日上限' }), { key: 'ArrowDown' })
  expect(await screen.findByRole('option', { name: '100 次 / 天' })).toBeTruthy()
  expect(screen.getByRole('option', { name: '10,000 次 / 天' })).toBeTruthy()
  expect(screen.queryByRole('option', { name: '0 次 / 天' })).toBeNull()
  fireEvent.click(screen.getByRole('option', { name: '500 次 / 天' }))
  expect(rest).toHaveBeenCalledOnce()
  fireEvent.click(screen.getByRole('button', { name: '保存采集上限' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/collection-budget', { method: 'PUT', body: { version: 4, limit: 500 } }))
  expect(await screen.findByText('每日采集上限已保存为 500 次，当天已用次数保留。')).toBeTruthy()
  expect(rest.mock.calls.every(([path]) => path === '/collection-budget')).toBe(true)
})

it('does not normalize a historical low limit just by opening settings', () => {
  const changed = vi.fn()
  render(<SourceLimitField onChange={changed} value={30} />)
  expect(screen.getByText('这是历史额度，请选择 100–10,000 之间的新上限。')).toBeTruthy()
  expect(changed).not.toHaveBeenCalled()
})
