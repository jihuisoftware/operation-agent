import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import type { Api, Guest } from './types'
import { useWebTakeover } from './use-web-takeover'

afterEach(cleanup)

function setup(api: Api, pending: Promise<unknown> | null = null) {
  const guest = { style: { pointerEvents: 'none' } } as unknown as Guest
  const status = vi.fn()
  const execution = { current: { pending } }
  const hook = renderHook(() => useWebTakeover({ api, guest, worker: 'window', execution, onStatus: status }))

  return { ...hook, guest, status }
}

it('retains manual intent for heartbeats until an explicit release', async () => {
  const api = vi.fn(async () => ({})) as unknown as Api
  const { result, guest } = setup(api)
  await act(async () => { await result.current.takeOver() })
  expect(result.current.manual.current).toBe(true)
  expect(guest.style.pointerEvents).toBe('auto')
  const old = result.current.revision.current
  await act(async () => { await result.current.release() })
  act(() => result.current.reconcile({ held: true, owned: true }, old))
  expect(result.current.manual.current).toBe(false)
  expect(guest.style.pointerEvents).toBe('none')
})

it('ignores a held response requested while release was still pending', async () => {
  let finish!: () => void
  const released = new Promise<void>(resolve => { finish = resolve })

  const api = vi.fn(async (_path, body) => {
    if (!body.active) { await released }

    return {}
  }) as unknown as Api

  const { result } = setup(api)
  await act(async () => { await result.current.takeOver() })
  let pending!: Promise<void>
  act(() => { pending = result.current.release() })
  const duringRelease = result.current.revision.current
  await act(async () => { finish(); await pending })
  act(() => result.current.reconcile({ held: true, owned: true }, duringRelease))
  expect(result.current.manual.current).toBe(false)
})

it('does not re-enable an old takeover after the user releases while a command is ending', async () => {
  let finish!: () => void
  const command = new Promise<void>(resolve => { finish = resolve })
  const api = vi.fn(async () => ({})) as unknown as Api
  const { result, guest } = setup(api, command)
  let taking!: Promise<void>
  await act(async () => { taking = result.current.takeOver(); await Promise.resolve() })
  await act(async () => { await result.current.release(); finish(); await taking })
  expect(result.current.manual.current).toBe(false)
  expect(guest.style.pointerEvents).toBe('none')
})
