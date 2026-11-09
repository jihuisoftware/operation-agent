import { host, type PluginContext } from '@hermes/plugin-sdk'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { executeBrowser } from './browser'
import { $loginRequest } from './login-state'
import { $operationsBrowserActivity, $showOperationsBrowser } from './state'
import type { Guest } from './types'
import { OperationsWorker } from './worker'
import { $workspaceBrowser, $workspaces, chooseScope } from './workspace-state'

const workerOwner = { connectionId: 'local', profile: 'one', account_id: 'account', business_id: 'b', topic_id: 't' }
const catalog = { businesses: [{ id: 'b', name: '业务', account: 'account', archived: 0 }], topics: [{ id: 't', business_id: 'b', name: '主题', archived: 0 }], accounts: [{ id: 'account', identity: '' }], paused: false }

vi.mock('@hermes/plugin-sdk', async importOriginal => {
  const sdk = await importOriginal<Record<string, unknown>>()
  const { atom } = await import('nanostores')
  const { useStore } = await import('@nanostores/react')

  return {
    ...sdk,
    host: {
      state: { requestOwner: atom({ connectionId: 'local', profile: 'one' }) },
      notify: vi.fn(),
      openWorkspace: vi.fn(() => vi.fn()),
      paneVisibility: () => atom(true)
    },
    useValue: useStore
  }
})
vi.mock('./browser', () => ({ executeBrowser: vi.fn() }))
vi.mock('./execution-clock', () => ({
  createExecutionClock: (tick: () => void) => {
    const timer = setInterval(tick, 2000)

    return {
      dispose: () => clearInterval(timer),
      sleep: (ms: number) => new Promise(resolve => setTimeout(resolve, ms))
    }
  }
}))

afterEach(() => {
  cleanup()
  $workspaces.set({})
  $workspaceBrowser.set({})
  $loginRequest.set(null)
  $showOperationsBrowser.set(false)
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

it('takes over before returning from the creator page and keeps the same account guest for home navigation', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('crypto', { randomUUID: () => 'worker', subtle: { digest: async () => new Uint8Array([1, 2]).buffer } })
  let allowTakeover!: () => void

  const rest = vi.fn(async (path: string) => {
    if (path === '/workspaces') { return catalog }

    if (path.startsWith('/worker/takeover?')) { await new Promise<void>(resolve => { allowTakeover = resolve }) }

    return { ok: true }
  })

  const { container } = render(<OperationsWorker ctx={{ rest } as unknown as PluginContext} />)
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1)
    $showOperationsBrowser.set(true)
  })
  const guest = container.querySelector('webview') as Guest
  const partition = guest.getAttribute('partition')
  Object.assign(guest, { canGoBack: () => true, goBack: vi.fn(), loadURL: vi.fn(async () => {}) })
  fireEvent.click(screen.getByRole('button', { name: '返回上一页' }))
  await act(async () => { await vi.advanceTimersByTimeAsync(1) })
  expect(guest.goBack).not.toHaveBeenCalled()
  await act(async () => { allowTakeover() })
  expect(guest.goBack).toHaveBeenCalledOnce()
  fireEvent.click(screen.getByRole('button', { name: '返回首页' }))
  await act(async () => { await vi.advanceTimersByTimeAsync(1); allowTakeover() })
  expect(guest.loadURL).toHaveBeenCalledWith('https://www.xiaohongshu.com/explore')
  expect(container.querySelector('webview')).toBe(guest)
  expect(guest.getAttribute('partition')).toBe(partition)
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
    if (path === '/workspaces') { return catalog }

    if (path === '/workspaces/worker/poll') {
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
    await vi.advanceTimersByTimeAsync(1)
    Object.assign(container.querySelector('webview')!, { getURL: () => 'https://www.xiaohongshu.com/explore' })
    await vi.advanceTimersByTimeAsync(1999)
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
    '/workspaces/worker/poll',
    expect.objectContaining({
      body: { worker: 'worker', busy: true, takeover: false, account_id: 'account' },
      owner: workerOwner
    })
  )
  expect(executeBrowser).toHaveBeenCalledTimes(1)
  expect($operationsBrowserActivity.get()).toEqual({
    owner: workerOwner,
    kind: 'publish'
  })
  await act(async () => {
    finish({ state: 'unknown', error: '提交超时' })
  })
  expect(rest).toHaveBeenCalledWith(
    '/worker/ack?business_id=b&topic_id=t',
    expect.objectContaining({ body: { id: 'task', worker: 'worker', result: { state: 'unknown', error: '提交超时' } } })
  )
  expect(host.notify).not.toHaveBeenCalled()
  expect($operationsBrowserActivity.get()).toBeNull()
})

it('opens the operating homepage in the persistent login partition after mounting', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('crypto', { randomUUID: () => 'worker', subtle: { digest: async () => new Uint8Array([1, 2]).buffer } })
  const rest = vi.fn(async (path: string) => path === '/workspaces' ? catalog : { command: null })
  const { container } = render(<OperationsWorker ctx={{ rest } as unknown as PluginContext} />)
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1)
  })
  const guest = container.querySelector('webview')!
  expect(guest.getAttribute('src')).toBe('https://www.xiaohongshu.com/explore')
  expect(guest.getAttribute('partition')).toBe('persist:operations-0102')
})

it('retains the page and login partition when the same owner receives a new API context', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('crypto', { randomUUID: () => 'worker', subtle: { digest: async () => new Uint8Array([1, 2]).buffer } })
  const rest = vi.fn(async (path: string) => path === '/workspaces' ? catalog : { command: null })
  const { container, rerender } = render(<OperationsWorker ctx={{ rest } as unknown as PluginContext} />)
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1)
  })
  const guest = container.querySelector('webview')!
  guest.setAttribute('src', 'https://www.zhihu.com/')
  rerender(<OperationsWorker ctx={{ rest } as unknown as PluginContext} />)
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1)
  })
  expect(container.querySelector('webview')).toBe(guest)
  expect(guest.getAttribute('src')).toBe('https://www.zhihu.com/')
  expect(guest.getAttribute('partition')).toBe('persist:operations-0102')
})

it('shows navigation failure with a recovery action instead of an unexplained blank page', async () => {
  $showOperationsBrowser.set(true)
  vi.useFakeTimers()
  vi.stubGlobal('crypto', { randomUUID: () => 'worker', subtle: { digest: async () => new Uint8Array([1, 2]).buffer } })
  const rest = vi.fn(async (path: string) => path === '/workspaces' ? catalog : { command: null })
  const { container } = render(<OperationsWorker ctx={{ rest } as unknown as PluginContext} />)
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1)
  })
  const guest = container.querySelector('webview') as Guest
  guest.loadURL = vi.fn(async () => {})
  guest.executeJavaScript = vi.fn(async () => undefined)

  const error = Object.assign(new Event('did-fail-load'), {
    isMainFrame: true,
    errorCode: -105,
    errorDescription: '无法解析地址'
  })

  act(() => {
    guest.dispatchEvent(error)
  })
  expect(screen.getByRole('alert').textContent).toContain('无法解析地址')
  fireEvent.click(screen.getByRole('button', { name: '重新打开网页' }))
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1)
  })
  expect(guest.loadURL).toHaveBeenCalledWith('https://www.xiaohongshu.com/explore')
  act(() => {
    guest.dispatchEvent(new Event('dom-ready'))
  })
  expect(screen.queryByRole('alert')).toBeNull()
  expect(screen.queryByText('正在加载网页，沿用已保存的登录状态…')).toBeNull()
})

it('opens independent platform pages after takeover and keeps hidden pages reporting login changes', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('crypto', { randomUUID: () => 'worker', subtle: { digest: async () => new Uint8Array([1, 2]).buffer } })
  const order: string[] = []

  const rest = vi.fn(async (path: string, options?: { method?: string; body?: any }) => {
    if (path === '/workspaces') { return catalog }

    if (path === '/workspaces/worker/poll') {
      return { command: null }
    }

    if (path === '/worker/takeover?business_id=b&topic_id=t') {
      expect(options?.body.active).toBe(true)
      order.push('pause')

      return { version: 2 }
    }

    if (path === '/policy?business_id=b&topic_id=t') {
      return { version: 1, policy: { enabled: false, paused: false } }
    }

    return { ok: true }
  })

  const { container } = render(<OperationsWorker ctx={{ rest } as unknown as PluginContext} />)
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2000)
  })
  const guest = container.querySelector('webview') as Guest
  guest.loadURL = vi.fn(async () => {
    order.push('load')
  })
  await act(async () => {
    $loginRequest.set({
      owner: workerOwner,
      platform: 'zhihu',
      url: 'https://www.zhihu.com/',
      id: 'login'
    })
  })
  await act(async () => { await vi.advanceTimersByTimeAsync(1) })
  expect(order).toEqual(['pause'])
  expect(container.querySelector('webview')).toBe(guest)
  expect(guest.loadURL).not.toHaveBeenCalled()
  const zhihu = container.querySelectorAll('webview')[1] as Guest
  expect(zhihu.getAttribute('src')).toBe('https://www.zhihu.com/')
  expect(zhihu.getAttribute('partition')).toBe(guest.getAttribute('partition'))
  Object.assign(guest, {
    getURL: () => 'https://www.xiaohongshu.com/explore',
    executeJavaScript: vi.fn(async () => ({ state: 'logged_out', account_id: '' }))
  })
  Object.assign(zhihu, {
    getURL: () => 'https://www.zhihu.com/',
    executeJavaScript: vi.fn(async () => ({ state: 'logged_in', account_id: 'zhihu-me' })),
    loadURL: vi.fn()
  })
  await act(async () => {
    guest.dispatchEvent(new Event('dom-ready'))
    zhihu.dispatchEvent(new Event('dom-ready'))
  })
  expect(rest).toHaveBeenCalledWith(
    '/platforms/observe?business_id=b&topic_id=t',
    expect.objectContaining({
      owner: workerOwner,
      body: { worker: 'worker', platform: 'zhihu', state: 'logged_in', account_id: 'zhihu-me' }
    })
  )
  vi.mocked(guest.executeJavaScript).mockResolvedValue({ state: 'logged_in', account_id: 'xhs-me' })
  await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
  expect(rest).toHaveBeenCalledWith('/platforms/observe?business_id=b&topic_id=t', expect.objectContaining({
    body: { worker: 'worker', platform: 'xiaohongshu', state: 'logged_in', account_id: 'xhs-me' }
  }))
  fireEvent.click(screen.getByRole('button', { name: '小红书' }))
  expect(screen.getByRole('region', { name: '小红书页面' })).toBeTruthy()
  expect(screen.queryByRole('region', { name: '知乎页面' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '知乎' }))
  expect(screen.getByRole('region', { name: '知乎页面' })).toBeTruthy()
  await act(async () => { $loginRequest.set({ owner: workerOwner, platform: 'zhihu', url: 'https://www.zhihu.com/', id: 'again' }) })
  expect([...container.querySelectorAll('webview')]).toEqual([guest, zhihu])
  expect(zhihu.loadURL).not.toHaveBeenCalled()
  expect(executeBrowser).not.toHaveBeenCalled()
})

it('keeps a background account executing after switching businesses and acknowledges its original topic', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('crypto', { randomUUID: () => 'worker', subtle: { digest: async () => new Uint8Array([1, 2]).buffer } })
  let finish!: (result: { state: string; error: string }) => void
  vi.mocked(executeBrowser).mockImplementation(() => new Promise(resolve => { finish = resolve }))

  const multiple = {
    ...catalog,
    businesses: [...catalog.businesses, { id: 'other', name: '其他业务', account: 'other-account', archived: 0 }],
    topics: [...catalog.topics, { id: 'other-topic', business_id: 'other', name: '另一个主题', archived: 0 }],
    accounts: [...catalog.accounts, { id: 'other-account', identity: '' }]
  }

  let delivered = false

  const rest = vi.fn(async (path: string, options?: { body?: any }) => {
    if (path === '/workspaces') { return multiple }

    if (path === '/workspaces/worker/poll' && options?.body.account_id === 'account' && !delivered) {
      delivered = true

      return { command: { id: 'owned-command', kind: 'publish', payload: {}, scope: { business_id: 'b', topic_id: 't' }, expires: Date.now() / 1000 + 120 } }
    }

    return { command: null }
  })

  const { container } = render(<OperationsWorker ctx={{ rest } as unknown as PluginContext} />)
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1)
    container.querySelectorAll('webview').forEach(guest => Object.assign(guest, { getURL: () => 'https://www.xiaohongshu.com/explore' }))
    await vi.advanceTimersByTimeAsync(1999)
  })
  const guests = [...container.querySelectorAll('webview')]
  expect(guests).toHaveLength(2)
  act(() => chooseScope(host.state.requestOwner.get(), { business_id: 'other', topic_id: 'other-topic' }))
  expect([...container.querySelectorAll('webview')]).toEqual(guests)
  await act(async () => finish({ state: 'confirmed', error: '' }))
  expect(rest).toHaveBeenCalledWith('/worker/ack?business_id=b&topic_id=t', expect.objectContaining({ body: expect.objectContaining({ id: 'owned-command' }) }))
  expect(executeBrowser).toHaveBeenCalledTimes(1)
})

it('loads other platform pages only on demand and recovers the failed platform without replacing its siblings', async () => {
  vi.useFakeTimers()
  let id = 0
  vi.stubGlobal('crypto', { randomUUID: () => `id-${++id}`, subtle: { digest: async () => new Uint8Array([1, 2]).buffer } })
  $showOperationsBrowser.set(true)
  const rest = vi.fn(async (path: string) => path === '/workspaces' ? catalog : { command: null })
  const { container } = render(<OperationsWorker ctx={{ rest } as unknown as PluginContext} />)
  await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
  const first = container.querySelector('webview')!
  expect(container.querySelectorAll('webview')).toHaveLength(1)

  const pages = [
    ['知乎', 'https://www.zhihu.com/'],
    ['B 站', 'https://www.bilibili.com/'],
    ['微信公众号后台', 'https://mp.weixin.qq.com/'],
    ['抖音', 'https://www.douyin.com/']
  ]

  for (const [name, url] of pages) {
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name }))
      await vi.advanceTimersByTimeAsync(1)
    })
    const guest = container.querySelectorAll('webview')[pages.findIndex(p => p[0] === name) + 1] as Guest
    expect(guest.getAttribute('src')).toBe(url)
    expect(screen.getByRole('region', { name: `${name}页面` })).toBeTruthy()
    Object.assign(guest, { getURL: () => url, loadURL: vi.fn(async () => {}) })
  }

  const guests = [...container.querySelectorAll('webview')]
  expect(guests).toHaveLength(5)
  const douyin = guests[4] as Guest
  act(() => douyin.dispatchEvent(Object.assign(new Event('did-fail-load'), {
    isMainFrame: true, errorCode: -105, errorDescription: '连接失败'
  })))
  expect(screen.getByRole('alert').textContent).toContain('连接失败')
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '重新打开网页' })) })
  expect(douyin.loadURL).toHaveBeenCalledWith('https://www.douyin.com/')
  expect([...container.querySelectorAll('webview')]).toEqual(guests)
  expect(guests[0]).toBe(first)
  fireEvent.click(screen.getByRole('button', { name: '知乎' }))
  expect(screen.queryByRole('alert')).toBeNull()
  expect(rest.mock.calls.filter(([path]) => path === '/workspaces/worker/poll')).toHaveLength(1)
})


it('acknowledges a stable login interruption and ignores a late old execution result', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('crypto', { randomUUID: () => 'worker', subtle: { digest: async () => new Uint8Array([1, 2]).buffer } })
  let finish!: (value: any) => void
  vi.mocked(executeBrowser).mockImplementation(() => new Promise(resolve => { finish = resolve }))
  let delivered = false

  const rest = vi.fn(async (path: string) => {
    if (path === '/workspaces') { return catalog }

    if (path === '/workspaces/worker/poll') {
      if (!delivered) {
        delivered = true

        return { command: { id: 'login-task', kind: 'inbox', payload: { account_id: 'me' }, expires: Date.now() / 1000 + 120 } }
      }

      return { command: null }
    }

    return { ok: true }
  })

  const { container } = render(<OperationsWorker ctx={{ rest } as unknown as PluginContext} />)
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1)
    Object.assign(container.querySelector('webview')!, { getURL: () => 'https://www.xiaohongshu.com/explore',
      executeJavaScript: async () => ({ state: 'logged_out', account_id: '' }) })
    await vi.advanceTimersByTimeAsync(1999)
  })
  await act(async () => { container.querySelector('webview')!.dispatchEvent(new Event('dom-ready')); await vi.advanceTimersByTimeAsync(1) })
  const acknowledgements = () => rest.mock.calls.filter(([path]) => path.startsWith('/worker/ack?'))
  expect(acknowledgements()).toHaveLength(0)
  await act(async () => { await vi.advanceTimersByTimeAsync(4000) })
  expect(acknowledgements()).toHaveLength(1)
  expect(rest).toHaveBeenCalledWith(expect.stringContaining('/worker/ack'), expect.objectContaining({
    body: { id: 'login-task', worker: 'worker', result: expect.objectContaining({ error_code: 'AUTH_REQUIRED', state: 'blocked', submitted: false }) }
  }))
  await act(async () => { finish({ state: 'confirmed' }); await vi.advanceTimersByTimeAsync(1) })
  expect(acknowledgements()).toHaveLength(1)
})

it('shows an idle connection after a successful heartbeat instead of waiting for a command', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('crypto', { randomUUID: () => 'worker', subtle: { digest: async () => new Uint8Array([1, 2]).buffer } })
  const rest = vi.fn(async (path: string) => path === '/workspaces' ? catalog : { command: null })
  render(<OperationsWorker ctx={{ rest } as unknown as PluginContext} />)
  await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
  expect(screen.getByText('执行窗口已连接，等待任务')).toBeTruthy()
  expect(screen.queryByText('等待连接')).toBeNull()
})
