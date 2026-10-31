import { afterEach, expect, it, vi } from 'vitest'

import { setApiRequestConnection, setApiRequestProfile } from '@/hermes'

import { pluginRest } from './plugins'

afterEach(() => {
  setApiRequestConnection(null)
  setApiRequestProfile(null)
  Reflect.deleteProperty(window, 'hermesDesktop')
})

it('keeps background plugin writes on their captured owner after the UI switches profiles', async () => {
  const api = vi.fn(async (_request: unknown) => ({ ok: true }))
  Object.defineProperty(window, 'hermesDesktop', { configurable: true, value: { api } })
  setApiRequestConnection('new-connection')
  setApiRequestProfile('new-profile')
  await pluginRest('operations', '/worker/ack', {
    owner: { connectionId: 'old-connection', profile: 'old-profile' },
    method: 'POST',
    body: { id: 'task' }
  })
  expect(api).toHaveBeenCalledWith(expect.objectContaining({ connectionId: 'old-connection', profile: 'old-profile' }))
  await pluginRest('operations', '/worker/ack', { owner: { connectionId: null, profile: null }, method: 'POST' })
  expect(api.mock.calls[1][0]).not.toHaveProperty('profile')
  expect(api.mock.calls[1][0]).not.toHaveProperty('connectionId')
})
