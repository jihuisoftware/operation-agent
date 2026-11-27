/**
 * The workspace pane is the one host whose zone paints the page header
 * (#123597). These read the REAL `workspace` contribution registered by the
 * controller, render it through the real tree renderer, and check that a
 * `WorkspacePageHeaderControl` lands in that header — and renders inline
 * wherever the host context is absent.
 */
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { type ReactNode, useEffect } from 'react'
import { Link, MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TreeGroup } from '@/components/pane-shell/tree/renderer/tree-group'
import { stubResizeObserver } from '@/test/jsdom'

import { $workspaceIsPage, ROUTES_AREA, WORKSPACE_PAGE_HEADER_AREA } from '../routes'
import { useOverlayRouting } from '../shell/hooks/use-overlay-routing'

import { ContribWiringContext, WiredPane } from './context'
import type { WiringApi } from './types'
import { WorkspacePageHeaderControl } from './workspace-page-header'

const { registry } = await import('@/contrib/registry')

await import('./controller')

const workspace = () => registry.getArea('panes').find(c => c.id === 'workspace')!

const wiring = (chatRoutes: ReactNode) => ({ chatRoutes }) as unknown as WiringApi

const probe = (
  <WorkspacePageHeaderControl id="probe:ctl">
    <button type="button">probe-ctl</button>
  </WorkspacePageHeaderControl>
)

const workspaceZone = (chatRoutes: ReactNode) => (
  <ContribWiringContext.Provider value={wiring(chatRoutes)}>
    <TreeGroup
      leftEdge
      node={{ active: 'workspace', id: 'main-zone', panes: ['workspace'], type: 'group' }}
      rightEdge
    />
  </ContribWiringContext.Provider>
)

afterEach(() => {
  cleanup()
  act(() => $workspaceIsPage.set(false))
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('workspace page header host', () => {
  it('drops the chat tab when the page at the current URL registers after startup', () => {
    vi.stubGlobal('CSS', { escape: (value: string) => value })
    stubResizeObserver()

    function Shell() {
      useOverlayRouting()
      return workspaceZone(<Link to="/">返回聊天</Link>)
    }

    const { container } = render(
      <MemoryRouter initialEntries={['/late-overview']}>
        <Shell />
      </MemoryRouter>
    )
    const tabStrip = () => container.querySelector('[data-zone-tabstrip]')
    expect(tabStrip()).not.toBeNull()

    let dispose!: () => void
    act(() => {
      dispose = registry.register({
        area: ROUTES_AREA,
        id: 'test:late-overview',
        data: { path: '/late-overview' },
        render: () => null
      })
    })
    try {
      expect(tabStrip()).toBeNull()
      fireEvent.click(screen.getByRole('link', { name: '返回聊天' }))
      expect(tabStrip()).not.toBeNull()
    } finally {
      act(() => dispose())
    }
  })

  it('projects a hosted control into the painted page header, not the pane body', () => {
    vi.stubGlobal('CSS', { escape: (value: string) => value })
    stubResizeObserver()
    act(() => $workspaceIsPage.set(true))

    const { container } = render(workspaceZone(probe))
    const header = container.querySelector<HTMLElement>('[data-panel-page-header]')

    expect(header).not.toBeNull()
    expect(within(header!).getAllByRole('button', { name: 'probe-ctl' })).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: 'probe-ctl' })).toHaveLength(1)
  })

  it('keeps one render identity and never remounts the pane across re-registration', () => {
    vi.stubGlobal('CSS', { escape: (value: string) => value })
    stubResizeObserver()

    let mounts = 0

    function MountCounter() {
      useEffect(() => {
        mounts += 1
      }, [])

      return <span>counter</span>
    }

    const render0 = workspace().render

    render(workspaceZone(<MountCounter />))

    act(() => $workspaceIsPage.set(true))
    expect(workspace().render).toBe(render0)
    act(() => $workspaceIsPage.set(false))
    expect(workspace().render).toBe(render0)

    const dispose = registry.register({ area: WORKSPACE_PAGE_HEADER_AREA, id: 'probe:area', render: () => null })
    act(() => $workspaceIsPage.set(true))
    act(() => dispose())

    expect(workspace().render).toBe(render0)
    expect(mounts).toBe(1)
  })

  it('renders inline and registers nothing outside the host (the HUD shape)', () => {
    const { container } = render(
      <ContribWiringContext.Provider value={wiring(probe)}>
        <WiredPane part="chatRoutes" />
      </ContribWiringContext.Provider>
    )

    expect(within(container).getAllByRole('button', { name: 'probe-ctl' })).toHaveLength(1)
    expect(registry.getArea(WORKSPACE_PAGE_HEADER_AREA)).toHaveLength(0)
  })
})
