import { host, type PluginContext } from '@hermes/plugin-sdk'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import type { WritableAtom } from 'nanostores'
import { afterEach, expect, it, vi } from 'vitest'

import { AccountsPage } from './accounts'

vi.mock('@hermes/plugin-sdk', async importOriginal => {
  const sdk = await importOriginal<Record<string, unknown>>()
  const { atom } = await import('nanostores')

  return { ...sdk, host: { state: { requestOwner: atom({ connectionId: 'local', profile: 'one' }) } } }
})

afterEach(cleanup)

it('shows account status independently and rebinds requests when the Profile changes', async () => {
  const rest = vi.fn(async (_path: string) => ({ worker_online: false, platforms: [] }))
  render(<AccountsPage ctx={{ rest } as unknown as PluginContext} />)
  expect(screen.getByRole('heading', { name: '账号登录' })).toBeTruthy()
  await waitFor(() =>
    expect(rest).toHaveBeenCalledWith('/platforms', {
      owner: { connectionId: 'local', profile: 'one' }
    })
  )
  // The real host exposes a readonly atom; the fixture owns the mutable store.
  const owner = host.state.requestOwner as WritableAtom<{ connectionId: string; profile: string }>
  act(() => owner.set({ connectionId: 'remote', profile: 'two' }))
  await waitFor(() =>
    expect(rest).toHaveBeenCalledWith('/platforms', {
      owner: { connectionId: 'remote', profile: 'two' }
    })
  )
  expect(rest.mock.calls.every(([path]) => path === '/platforms')).toBe(true)
})
