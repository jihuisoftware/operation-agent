import { afterEach, expect, it, vi } from 'vitest'

import { createBrowserPower, interruption } from './browser-power'
type BrowserPowerApi = NonNullable<NonNullable<Window['hermesDesktop']>['browserPower']>
type BrowserPowerEntry = Awaited<ReturnType<BrowserPowerApi['begin']>>

afterEach(() => { vi.unstubAllGlobals() })

const entry: BrowserPowerEntry = { connectionId: 'local', profile: 'one', account_id: 'account', business_id: 'b', topic_id: 't',
  command_id: 'cmd', worker: 'old-worker', guest_id: 1, epoch: 'before-sleep', expires: 123,
  phase: 'read_only', interrupted: true, reason: 'SYSTEM_SUSPENDED', sleep_started_at: 100 }

it('replays interruption before one read-only probe, without clearing a block or resuming work', async () => {
  const acknowledged = vi.fn()

  const state = vi.fn().mockResolvedValueOnce({ epoch: 'wake', suspended: false, slept: true, entries: [entry] })
    .mockResolvedValue({ epoch: 'wake', suspended: false, slept: true, entries: [] })

  window.hermesDesktop = { browserPower: { state, acknowledged, onChange: () => () => {} } as unknown as BrowserPowerApi } as Window['hermesDesktop']
  const api = vi.fn().mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce({ state: 'ready', detail: '账号已确认；等待手动继续' })
  const power = createBrowserPower(entry, api, { current: { pending: null, worker: 'new-worker' } }, vi.fn())
  expect(await power.beforePoll(false)).toBe(false)
  expect(await power.beforePoll(false)).toBe(true)
  expect(api.mock.calls.map(call => call[0])).toEqual(['/worker/interrupted?business_id=b&topic_id=t', '/workspaces/worker/revalidate'])
  expect(acknowledged).toHaveBeenCalledWith(entry, 'cmd')
  await power.beforePoll(false)
  expect(api).toHaveBeenCalledTimes(2)
  power.dispose()
})

it('never probes while a human owns the page and keeps submission uncertainty', async () => {
  const state = vi.fn()
  window.hermesDesktop = { browserPower: { state, onChange: () => () => {} } as unknown as BrowserPowerApi } as Window['hermesDesktop']
  const power = createBrowserPower(entry, vi.fn(), { current: { pending: null } }, vi.fn())
  expect(await power.beforePoll(true)).toBe(true)
  expect(state).not.toHaveBeenCalled()
  expect(interruption({ ...entry, phase: 'submission_started' })).toMatchObject({ state: 'unknown', submitted: true })
  power.dispose()
})
