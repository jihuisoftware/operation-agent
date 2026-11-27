import { host, type CronBlueprintOwner, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { atom, computed } from 'nanostores'
import { useEffect } from 'react'

import { $loginNavigation, $loginRequest, $loginStatusRevision, loginLabels, sameLoginOwner, type PlatformLogins } from './login-state'
import { $workspaces, ownerKey, scopeKey, scopePath } from './workspace-state'

const $scope = computed([host.state.requestOwner, $workspaces], (owner, workspaces) => {
  const state = workspaces[ownerKey(owner)]
  const selected = state?.selected
  if (!selected) return null
  const account_id = state.catalog?.businesses.find(b => b.id === selected.business_id)?.account
  return { selected, owner: { ...owner, account_id }, key: JSON.stringify([scopeKey(owner, selected), account_id]) }
})
const $status = atom<{ key: string; attention?: string; unavailable?: boolean } | null>(null)

export const $loginActivity = computed(
  [$scope, $loginNavigation, $loginRequest, $status],
  (scope, navigation, request, status) => ({
    running: scope && navigation && request && sameLoginOwner(scope.owner, request.owner) ? 1 : 0,
    attention: status && status.key === scope?.key ? status.attention : undefined,
    unavailable: status?.key === scope?.key && status?.unavailable
  })
)

function attention(data: PlatformLogins) {
  return data.platforms.flatMap(p => {
    const state = p.account_mismatch ? 'mismatch' : p.observed_state === 'verification' ? 'verification' : p.state
    return ['logged_out', 'verification', 'mismatch'].includes(state) ? [p.name + '：' + loginLabels[state]] : []
  }).join('；')
}

export function useSidebarLoginStatus(ctx: PluginContext, owner: CronBlueprintOwner) {
  const scope = useValue($scope)
  const revision = useValue($loginStatusRevision)
  const key = scope?.key
  const selected = scope?.selected
  useEffect(() => {
    if (!key || !selected) return
    let sequence = 0
    const refresh = async () => {
      const request = ++sequence
      try {
        const data = await ctx.rest<PlatformLogins>(scopePath('/platforms', selected), { owner })
        if (request === sequence) $status.set({ key, attention: attention(data) })
      } catch {
        if (request === sequence) $status.set({ key, unavailable: true })
      }
    }
    void refresh()
    window.addEventListener('focus', refresh)
    return () => { sequence++; window.removeEventListener('focus', refresh) }
  }, [ctx, owner, key, selected, revision])
}
