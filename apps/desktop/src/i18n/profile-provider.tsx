import { useStore } from '@nanostores/react'
import { type ReactNode, useEffect } from 'react'

import { $gateway } from '@/store/gateway'
import { $activeGatewayProfile } from '@/store/profile'
import { $connection, $gatewayState } from '@/store/session'

import { syncBackendLocalePacks } from './backend-packs'
import { I18nProvider } from './context'
import { unregisterAppLocaleSource } from './registry'

/** Keep gateway/store imports outside the shared i18n context's import graph. */
export function ProfileI18nProvider({ children }: { children: ReactNode }) {
  const profile = useStore($activeGatewayProfile)
  const connection = useStore($connection)

  // The API captures the real read origin (including legacy profile overrides).
  // This is an invalidation key, not an explicit local/registry request pin.
  const scopeKey = JSON.stringify([
    connection?.connectionId ?? null,
    connection?.registryScoped ?? false,
    connection?.baseUrl,
    connection?.profile,
    profile
  ])

  useBackendLocalePacks(scopeKey)

  return <I18nProvider>{children}</I18nProvider>
}

/** Reconnects refresh Chinese copy; profile switches clear the previous overlay. */
function useBackendLocalePacks(scopeKey: string): void {
  const gatewayState = useStore($gatewayState)
  const open = gatewayState === 'open'

  useEffect(() => {
    unregisterAppLocaleSource('backend')
  }, [scopeKey])

  useEffect(() => {
    const gateway = $gateway.get()

    if (!open || !gateway) {
      return
    }

    let current = true

    void syncBackendLocalePacks(
      (method, params) => gateway.request(method, params),
      () => current
    )

    return () => {
      current = false
    }
  }, [open, scopeKey])
}
