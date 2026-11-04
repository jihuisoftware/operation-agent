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
