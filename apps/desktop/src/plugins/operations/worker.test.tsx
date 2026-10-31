import { host, type PluginContext } from '@hermes/plugin-sdk'
import { act, cleanup, render } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { executeBrowser } from './browser'
import { $showOperationsBrowser } from './state'
import { OperationsWorker } from './worker'

vi.mock('@hermes/plugin-sdk', async () => {
  const { atom } = await import('nanostores')
  const { useStore } = await import('@nanostores/react')

  return {
    host: { state: { requestOwner: atom({ connectionId: 'local', profile: 'one' }) }, notify: vi.fn() },
    useValue: useStore
  }
})
vi.mock('./browser', () => ({ executeBrowser: vi.fn() }))

afterEach(() => {
  cleanup()
  $showOperationsBrowser.set(false)
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

it('keeps the hidden guest mounted and heartbeats without claiming another task while busy', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('crypto', { randomUUID: () => 'worker', subtle: { digest: async () => new Uint8Array([1, 2]).buffer } })
  let finish!: (result: { state: string; error: string }) => void
  vi.mocked(executeBrowser).mockImplementation(
    () =>
      new Promise(resolve => {
        finish = resolve
      })
  )
  let delivered = false

  const rest = vi.fn(async (path: string, options?: { body?: unknown }) => {
    if (path === '/worker/poll') {
      const busy = (options?.body as { busy: boolean }).busy

      if (!delivered && !busy) {
        delivered = true

        return { command: { id: 'task', kind: 'publish', payload: {}, expires: Date.now() / 1000 + 120 } }
      }

      return { command: null }
    }

    return { ok: true }
  })

  const { container } = render(<OperationsWorker ctx={{ rest } as unknown as PluginContext} />)
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2000)
  })
  const guest = container.querySelector('webview')!
  expect(guest).toBeTruthy()
  expect(guest.getAttribute('webpreferences')).toContain('backgroundThrottling=no')
  expect(guest.getAttribute('partition')).toMatch(/^persist:operations-/)
  await act(async () => {
    $showOperationsBrowser.set(true)
  })
  await act(async () => {
    $showOperationsBrowser.set(false)
    await vi.advanceTimersByTimeAsync(2000)
  })
  expect(container.querySelector('webview')).toBe(guest)
  expect(rest).toHaveBeenCalledWith(
    '/worker/poll',
    expect.objectContaining({
      body: { worker: 'worker', busy: true },
      owner: { connectionId: 'local', profile: 'one' }
    })
  )
  expect(executeBrowser).toHaveBeenCalledTimes(1)
  await act(async () => {
    finish({ state: 'unknown', error: '提交超时' })
  })
  expect(rest).toHaveBeenCalledWith(
    '/worker/ack',
    expect.objectContaining({ body: { id: 'task', worker: 'worker', result: { state: 'unknown', error: '提交超时' } } })
  )
  expect(host.notify).not.toHaveBeenCalled()
})
