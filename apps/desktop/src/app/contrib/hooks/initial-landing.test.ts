import { expect, it, vi } from 'vitest'

import { registry } from '@/contrib/registry'
import { SIDEBAR_NAV_PREFS_AREA } from '@/store/sidebar-nav'

import { initialLanding } from './initial-landing'

it('waits for contributed home and preserves remembered navigation', () => {
  const dispose = registry.registerMany([
    { id: 'landing-test', area: SIDEBAR_NAV_PREFS_AREA, data: { home: '/overview' } }
  ])

  const navigate = vi.fn()
  const fresh = { route: null, routeSession: null, last: null, sessionCount: 0, pending: true, navigate }

  try {
    expect(initialLanding(fresh)).toBe(true)
    expect(navigate).not.toHaveBeenCalled()
    expect(initialLanding({ ...fresh, pending: false })).toBe(true)
    expect(navigate).toHaveBeenCalledWith('/overview', { replace: true })
    navigate.mockClear()
    expect(initialLanding({ ...fresh, pending: false, route: '/content' })).toBe(false)
    expect(initialLanding({ ...fresh, pending: false, last: 'session-1', sessionCount: 1 })).toBe(false)
    expect(navigate).not.toHaveBeenCalled()
  } finally {
    dispose()
  }
})
