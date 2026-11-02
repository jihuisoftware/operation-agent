import { registry } from '@/contrib/registry'
import { contributedHome, SIDEBAR_NAV_PREFS_AREA } from '@/store/sidebar-nav'

interface Landing {
  route: string | null
  routeSession: string | null
  last: string | null
  sessionCount: number
  pending: boolean
  navigate: (to: string, options?: { replace?: boolean }) => void
}

export function initialLanding({ route, routeSession, last, sessionCount, pending, navigate }: Landing): boolean {
  const fresh = !route && !last && sessionCount === 0

  if (pending && (fresh || routeSession)) {
    return true
  }

  const home = fresh ? contributedHome(registry.getArea(SIDEBAR_NAV_PREFS_AREA)) : null

  if (!home) {
    return false
  }

  navigate(home, { replace: true })

  return true
}
