import { webcrypto } from 'node:crypto'

import { cleanup, fireEvent, render, waitFor } from '@testing-library/react'
import { useRef } from 'react'
import { afterEach, expect, it, vi } from 'vitest'

import { useOperationsGuest } from './use-operations-guest'

function Viewer({ connectionId, profile, account_id, home }: { connectionId: string; profile: string; account_id?: string; home?: string }) {
  const container = useRef<HTMLDivElement>(null)
  useOperationsGuest({ connectionId, profile, account_id }, container, home)

  return <div ref={container} />
}

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('returns to the platform home when a guest has no history and surfaces back failures', async () => {
  vi.stubGlobal('crypto', webcrypto)

  function Navigation() {
    const container = useRef<HTMLDivElement>(null)
    const { back, error } = useOperationsGuest({ connectionId: 'local', profile: 'one', account_id: 'a' }, container, 'https://www.zhihu.com/')

    return <><button onClick={() => void back()}>返回</button><p>{error}</p><div ref={container} /></>
  }

  const view = render(<Navigation />)
  await waitFor(() => expect(view.container.querySelector('webview')).not.toBeNull())
  const guest = view.container.querySelector('webview')!
  const loadURL = vi.fn(async () => {})
  Object.assign(guest, { canGoBack: () => false, loadURL })
  fireEvent.click(view.getByRole('button', { name: '返回' }))
  await waitFor(() => expect(loadURL).toHaveBeenCalledWith('https://www.zhihu.com/'))
  Object.assign(guest, { canGoBack: () => true, goBack: () => { throw new Error('网页已关闭') } })
  fireEvent.click(view.getByRole('button', { name: '返回' }))
  expect(view.getByText('无法返回上一页：Error: 网页已关闭')).toBeTruthy()
})

it('installs the in-page publishing entry when the guest document is ready without enabling popups', async () => {
  vi.stubGlobal('crypto', webcrypto)
  const view = render(<Viewer account_id="a" connectionId="local" profile="one" />)
  await waitFor(() => expect(view.container.querySelector('webview')).not.toBeNull())
  const guest = view.container.querySelector('webview')!
  const page = window.document.implementation.createHTMLDocument()
  const listen = vi.spyOn(page, 'addEventListener')
  const navigate = vi.fn()

  const execute = vi.fn(async (code: string) => {
    // Execute the serialized guest script, including its defaults, across the webview boundary.
    Function('document', 'location', code)(page, { href: 'https://www.xiaohongshu.com/explore', assign: navigate })
  })

  Object.assign(guest, { executeJavaScript: execute })
  fireEvent(guest, new Event('dom-ready'))
  expect(execute).toHaveBeenCalledOnce()
  page.body.innerHTML = '<button class="publish-btn"><span>＋</span></button>'
  const listener = listen.mock.calls.find(([type]) => type === 'click')?.[1] as EventListener
  listener({ target: page.querySelector('span'), isTrusted: true, button: 0,
    preventDefault() {}, stopImmediatePropagation() {} } as unknown as Event)
  expect(navigate).toHaveBeenCalledWith('https://creator.xiaohongshu.com/publish/publish?source=official')
  expect(guest.hasAttribute('allowpopups')).toBe(false)
})

it('reuses the deployed cookie partition across remounts and isolates other owners', async () => {
  vi.stubGlobal('crypto', webcrypto)
  const first = render(<Viewer connectionId="local" profile="default" />)
  await waitFor(() => expect(first.container.querySelector('webview')).not.toBeNull())
  const partition = first.container.querySelector('webview')!.getAttribute('partition')
  // Existing installations already store their login in this partition.
  expect(partition).toBe('persist:operations-7691b732c9b8157a3ccafbc7af3208ff9a45e86cd5f1086a01f889e6c0e7a052')
  first.unmount()
  const next = render(<Viewer connectionId="local" profile="default" />)
  await waitFor(() => expect(next.container.querySelector('webview')).not.toBeNull())
  expect(next.container.querySelector('webview')!.getAttribute('partition')).toBe(partition)
  next.rerender(<Viewer connectionId="local" key="local-separate" profile="separate" />)
  await waitFor(() => expect(next.container.querySelector('webview')?.getAttribute('partition')).not.toBe(partition))
  await waitFor(() => expect(next.container.querySelector('webview')).not.toBeNull())
  const other = next.container.querySelector('webview')!.getAttribute('partition')
  next.rerender(<Viewer connectionId="remote" key="remote-separate" profile="separate" />)
  await waitFor(() => expect(next.container.querySelector('webview')).not.toBeNull())
  expect(next.container.querySelector('webview')!.getAttribute('partition')).not.toBe(other)
})

it('preserves existing account cookies across platform pages and isolates a second account', async () => {
  vi.stubGlobal('crypto', webcrypto)

  const view = render(<>
    <Viewer account_id="a" connectionId="local" profile="one" />
    <Viewer account_id="a" connectionId="local" home="https://www.zhihu.com/" profile="one" />
    <Viewer account_id="b" connectionId="local" home="https://www.zhihu.com/" profile="one" />
  </>)

  await waitFor(() => expect(view.container.querySelectorAll('webview')).toHaveLength(3))
  const [xhs, zhihu, other] = [...view.container.querySelectorAll('webview')]
  expect(xhs.getAttribute('partition')).toBe(zhihu.getAttribute('partition'))
  expect(other.getAttribute('partition')).not.toBe(zhihu.getAttribute('partition'))
  expect(zhihu.getAttribute('src')).toBe('https://www.zhihu.com/')
})


it('replaces an unusable guest while preserving its account cookie partition', async () => {
  vi.stubGlobal('crypto', webcrypto)

  function Recoverable() {
    const container = useRef<HTMLDivElement>(null)
    const { replace } = useOperationsGuest({ connectionId: 'local', profile: 'one', account_id: 'a' }, container)

    return <><button onClick={replace}>重建网页</button><div ref={container} /></>
  }

  const view = render(<Recoverable />)
  await waitFor(() => expect(view.container.querySelector('webview')).not.toBeNull())
  const old = view.container.querySelector('webview')!
  const partition = old.getAttribute('partition')
  fireEvent.click(view.getByRole('button', { name: '重建网页' }))
  await waitFor(() => expect(view.container.querySelector('webview')).not.toBe(old))
  await waitFor(() => expect(view.container.querySelector('webview')?.getAttribute('partition')).toBe(partition))
  expect(old.isConnected).toBe(false)
})

it('clears loading when navigation stops without delivering a second dom-ready event', async () => {
  vi.stubGlobal('crypto', webcrypto)

  function StatusViewer() {
    const container = useRef<HTMLDivElement>(null)
    const { loading } = useOperationsGuest({ connectionId: 'local', profile: 'one' }, container)

    return <><p>{loading ? '网页加载中' : '网页已加载'}</p><div ref={container} /></>
  }

  const view = render(<StatusViewer />)
  await waitFor(() => expect(view.container.querySelector('webview')).not.toBeNull())
  fireEvent(view.container.querySelector('webview')!, new Event('did-stop-loading'))
  expect(view.getByText('网页已加载')).toBeTruthy()
})
