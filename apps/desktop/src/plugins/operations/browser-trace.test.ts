import { expect, it, vi } from 'vitest'

import { createBrowserTrace } from './browser-trace'
import type { Api, BrowserCommand, Guest } from './types'

it('does not start an external action when its durable start cannot be saved', async () => {
  const operation = vi.fn(async () => ({ state: 'submitted' }))
  const api = vi.fn(async () => { throw new Error('台账不可用') })
  const trace = createBrowserTrace({ id: 'command' } as BrowserCommand, { getURL: () => 'https://www.xiaohongshu.com' } as Guest, api as Api, 'worker')
  await expect(trace.step('submit', operation)).rejects.toThrow('台账不可用')
  expect(operation).not.toHaveBeenCalled()
})

it('retains a failed completion record without retrying the submitted operation', async () => {
  const operation = vi.fn(async () => ({ state: 'submitted' }))
  const api = vi.fn().mockResolvedValueOnce({}).mockRejectedValueOnce(new Error('写入中断')).mockResolvedValue({})
  const guest = { getURL: () => 'https://www.xiaohongshu.com', executeJavaScript: async () => ({ title: '页面' }) } as unknown as Guest
  const trace = createBrowserTrace({ id: 'command' } as BrowserCommand, guest, api as Api, 'worker')
  await expect(trace.step('submit', operation)).rejects.toThrow('写入中断')
  expect(operation).toHaveBeenCalledTimes(1)
  expect(api).toHaveBeenLastCalledWith('/worker/steps', expect.objectContaining({ phase: 'failed', error: expect.stringContaining('写入中断') }))
})
