import { host } from '@hermes/plugin-sdk'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { WritableAtom } from 'nanostores'
import { afterEach, expect, it, vi } from 'vitest'

import { useBrowserDock } from './browser-dock'
import { $showOperationsBrowser } from './state'

vi.mock('@hermes/plugin-sdk', async () => {
  const { atom } = await import('nanostores')
  const shown = atom(true)

  return { host: { openWorkspace: vi.fn(() => vi.fn()), paneVisibility: () => shown } }
})

function Probe({ shown }: { shown: boolean }) {
  const visible = useBrowserDock(shown)

  return <p>{visible ? '已分栏显示' : '后台保留'}</p>
}

afterEach(() => { cleanup(); $showOperationsBrowser.set(false); (host.paneVisibility('pane') as WritableAtom<boolean>).set(true); vi.clearAllMocks() })

it('reserves a right-hand shell pane only when opened and releases it on hide', () => {
  const view = render(<Probe shown={false} />)
  expect(host.openWorkspace).not.toHaveBeenCalled()
  view.rerender(<Probe shown />)
  expect(screen.getByText('已分栏显示')).toBeTruthy()
  expect(host.openWorkspace).toHaveBeenCalledWith('operations-browser', expect.objectContaining({ dock: { pane: 'workspace', pos: 'right' } }))
  const close = vi.mocked(host.openWorkspace).mock.results[0].value
  view.rerender(<Probe shown={false} />)
  expect(close).toHaveBeenCalledTimes(1)
  expect(screen.getByText('后台保留')).toBeTruthy()
})

it('follows shell visibility and synchronizes the toolbar when the pane is closed', () => {
  $showOperationsBrowser.set(true)
  render(<Probe shown />)
  const options = vi.mocked(host.openWorkspace).mock.calls[0][1]
  act(() => (host.paneVisibility('pane') as WritableAtom<boolean>).set(false))
  expect(screen.getByText('后台保留')).toBeTruthy()
  act(() => (host.paneVisibility('pane') as WritableAtom<boolean>).set(true))
  expect(screen.getByText('已分栏显示')).toBeTruthy()
  render(<button onClick={options.onClose}>关闭分栏</button>)
  fireEvent.click(screen.getByText('关闭分栏'))
  expect($showOperationsBrowser.get()).toBe(false)
})
