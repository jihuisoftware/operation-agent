import { host } from '@hermes/plugin-sdk'
import { act, cleanup, render } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { $loginNavigation, $loginRequest, $loginWorker } from './login-state'
import { $showOperationsBrowser } from './state'
import type { Api, Guest } from './types'
import { usePlatformLogin } from './use-platform-login'

vi.mock('@hermes/plugin-sdk', async () => {
  const { useStore } = await import('@nanostores/react')

  return { useValue: useStore, host: { notify: vi.fn() } }
})
const owner = { connectionId: 'local', profile: 'one' }

function fixture() {
  const guest = window.document.createElement('div') as unknown as Guest
  window.document.body.append(guest)
  guest.getURL = vi.fn(() => 'https://www.xiaohongshu.com/explore')
  guest.loadURL = vi.fn(async () => undefined)
  guest.executeJavaScript = vi.fn(async () => ({ state: 'logged_in', account_id: 'me' }))
  const api = vi.fn(async () => ({ ok: true })) as unknown as Api
  const takeOver = vi.fn(async (): Promise<void> => undefined)

  function Monitor() {
    usePlatformLogin({ api, guest, owner, worker: 'window', takeOver })

    return null
  }

  const view = render(<Monitor />)

  return { guest, api, takeOver, ...view }
}

afterEach(() => {
  cleanup()
  window.document.body.innerHTML = ''
  $loginRequest.set(null)
  $loginWorker.set(null)
  $loginNavigation.set(null)
  $showOperationsBrowser.set(false)
  vi.useRealTimers()
  vi.clearAllMocks()
})

it('deduplicates unchanged DOM and sends one notification per login problem transition', async () => {
  vi.useFakeTimers()
  const { guest, api } = fixture()
  await act(async () => {
    guest.dispatchEvent(new Event('dom-ready'))
  })
  expect(api).toHaveBeenCalledWith('/platforms/observe', {
    worker: 'window',
    platform: 'xiaohongshu',
    state: 'logged_in',
    account_id: 'me'
  })
  await act(async () => {
    await vi.advanceTimersByTimeAsync(60000)
  })
  expect(api).toHaveBeenCalledTimes(1)
  vi.mocked(guest.executeJavaScript).mockResolvedValue({ state: 'logged_out', account_id: '' })
  await act(async () => {
    await vi.advanceTimersByTimeAsync(60000)
  })
  expect(api).toHaveBeenCalledTimes(2)
  expect(host.notify).toHaveBeenCalledTimes(1)
  expect(guest.loadURL).not.toHaveBeenCalled()
})

it('waits for takeover before navigating and ignores requests for another Profile', async () => {
  const { guest, takeOver } = fixture()
  let paused!: () => void
  takeOver.mockImplementation(
    () =>
      new Promise<void>(resolve => {
        paused = resolve
      })
  )
  const request = { owner, platform: 'xiaohongshu', url: 'https://www.xiaohongshu.com/explore', id: 'first' }
  await act(async () => {
    $loginRequest.set({ ...request, owner: { ...owner, profile: 'two' } })
  })
  expect(takeOver).not.toHaveBeenCalled()
  await act(async () => {
    $loginRequest.set({ ...request, id: 'second' })
  })
  expect(guest.loadURL).not.toHaveBeenCalled()
  await act(async () => {
    paused()
  })
  expect(guest.loadURL).toHaveBeenCalledWith(request.url)
  expect($showOperationsBrowser.get()).toBe(true)
})

it('drops an observation after navigation and does not navigate after its owner unmounts', async () => {
  const { guest, api, takeOver, unmount } = fixture()
  let inspected!: (value: unknown) => void
  vi.mocked(guest.executeJavaScript).mockImplementation(
    () =>
      new Promise(resolve => {
        inspected = resolve
      })
  )
  await act(async () => {
    guest.dispatchEvent(new Event('dom-ready'))
  })
  await act(async () => {
    guest.dispatchEvent(new Event('did-start-loading'))
    inspected({ state: 'logged_in', account_id: 'old' })
  })
  expect(api).not.toHaveBeenCalled()
  let paused!: () => void
  takeOver.mockImplementation(
    () =>
      new Promise<void>(resolve => {
        paused = resolve
      })
  )
  await act(async () => {
    $loginRequest.set({ owner, platform: 'xiaohongshu', url: 'https://www.xiaohongshu.com/explore', id: 'pending' })
  })
  unmount()
  expect($loginNavigation.get()).toBeNull()
  await act(async () => {
    paused()
  })
  expect(guest.loadURL).not.toHaveBeenCalled()
})

it('reports a completed SPA login within two seconds without waiting for navigation', async () => {
  vi.useFakeTimers()
  const { guest, api } = fixture()
  vi.mocked(guest.executeJavaScript).mockResolvedValue({ state: 'logged_out', account_id: '' })
  await act(async () => {
    guest.dispatchEvent(new Event('dom-ready'))
  })
  vi.mocked(guest.executeJavaScript).mockResolvedValue({ state: 'logged_in', account_id: 'mine' })
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2000)
  })
  expect(api).toHaveBeenLastCalledWith('/platforms/observe', {
    worker: 'window',
    platform: 'xiaohongshu',
    state: 'logged_in',
    account_id: 'mine'
  })
  expect(guest.loadURL).not.toHaveBeenCalled()
})
