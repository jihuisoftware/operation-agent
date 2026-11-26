import { host, type CronBlueprintOwner } from '@hermes/plugin-sdk'
import { atom } from 'nanostores'

import { $workspaceDirty, $workspaces, type OperationScope, ownerKey, scopeKey, scopePath } from './workspace-state'

export const WORKSPACES_PATH = '/operations/workspaces'

export function workspaceLink(view: 'plan' | 'history', scope?: OperationScope) {
  const path = view === 'plan' ? WORKSPACES_PATH + '?view=plan' : '/cron?tab=history&historyView=operations.ledger'

  return scope ? scopePath(path, scope) : path
}

export function currentWorkspaceLink(view: 'plan' | 'history', owner = host.state.requestOwner.get()) {
  return workspaceLink(view, $workspaces.get()[ownerKey(owner)]?.selected)
}

interface PendingLeave {
  key: string
  owner: string
  proceed: () => void
}
export const $pendingLeave = atom<PendingLeave | null>(null)

export function dirtyScope(owner: CronBlueprintOwner) {
  const scope = $workspaces.get()[ownerKey(owner)]?.selected
  const key = scope && scopeKey(owner, scope)

  return key && $workspaceDirty.get()[key] ? key : null
}

export function guardWorkspaceChange(owner: CronBlueprintOwner, action: () => void) {
  if (ownerKey(owner) !== ownerKey(host.state.requestOwner.get())) return
  const key = dirtyScope(owner)
  if (key) {
    $pendingLeave.set({ key, owner: ownerKey(owner), proceed: action })
  } else {
    action()
  }
}

export function discardAndContinue() {
  const pending = $pendingLeave.get()
  $pendingLeave.set(null)
  const owner = host.state.requestOwner.get()
  if (!pending || pending.owner !== ownerKey(owner) || pending.key !== dirtyScope(owner)) return
  $workspaceDirty.set({ ...$workspaceDirty.get(), [pending.key]: false })
  pending.proceed()
}
