import { type CronBlueprintOwner, type PluginContext } from '@hermes/plugin-sdk'
import { atom } from 'nanostores'

export interface OperationScope { business_id: string; topic_id: string }
export interface WorkspaceBusiness { id: string; name: string; category: string; archived: number; paused: number; account: string }
export interface WorkspaceTopic { id: string; business_id: string; name: string; archived: number }
export interface WorkspaceAccount { id: string; identity: string; conflict: string; held: number }
export interface WorkspaceCatalog { businesses: WorkspaceBusiness[]; topics: WorkspaceTopic[]; accounts: WorkspaceAccount[]; paused: boolean; selection?: OperationScope | null }
export interface WorkspaceState { catalog?: WorkspaceCatalog; selected?: OperationScope; error?: string }
export const $workspaces = atom<Record<string, WorkspaceState>>({})
export const $workspaceDirty = atom<Record<string, boolean>>({})
export const $workspaceBrowser = atom<Record<string, { business_id: string; account_id: string }>>({})

export function showAccount(owner: CronBlueprintOwner, account: string) {
  const key = ownerKey(owner)
  const business = $workspaces.get()[key]?.selected?.business_id

  if (business) { $workspaceBrowser.set({ ...$workspaceBrowser.get(), [key]: { business_id: business, account_id: account } }) }
}

export function ownerKey(owner: CronBlueprintOwner) { return JSON.stringify([owner.connectionId, owner.profile || 'default']) }

export function scopeKey(owner: CronBlueprintOwner, scope: OperationScope) { return JSON.stringify([ownerKey(owner), scope.business_id, scope.topic_id]) }

export function scopePath(path: string, scope: OperationScope) {
  const [pathname, query = ''] = path.split('?')
  const params = new URLSearchParams(query)
  params.set('business_id', scope.business_id)
  params.set('topic_id', scope.topic_id)

  return `${pathname}?${params}`
}

export function scopedContext(ctx: PluginContext, owner: CronBlueprintOwner, scope: OperationScope): PluginContext {
  return { ...ctx, rest: (path, options) => ctx.rest(scopePath(path, scope), { ...options, owner }) }
}

const routeWriters = new Map<string, (scope: OperationScope) => void>()

export function bindScopeRoute(owner: CronBlueprintOwner, write: (scope: OperationScope) => void) {
  const key = ownerKey(owner)
  routeWriters.set(key, write)

  return () => { if (routeWriters.get(key) === write) { routeWriters.delete(key) } }
}

export function chooseScope(owner: CronBlueprintOwner, selected: OperationScope, updateRoute = true) {
  const key = ownerKey(owner)
  $workspaces.set({ ...$workspaces.get(), [key]: { ...$workspaces.get()[key], selected } })

  if (updateRoute) { routeWriters.get(key)?.(selected) }
  void selectionWriters.get(key)?.(selected).catch(error => {
    $workspaces.set({ ...$workspaces.get(), [key]: { ...$workspaces.get()[key], error: `切换已完成，但记忆选择失败：${String(error)}` } })
  })
}

const loading = new Map<string, Promise<void>>()
const selectionWriters = new Map<string, (scope: OperationScope) => Promise<unknown>>()

export function loadWorkspaces(ctx: PluginContext, owner: CronBlueprintOwner) {
  const key = ownerKey(owner)
  selectionWriters.set(key, scope => ctx.rest('/workspaces/selection', { owner, method: 'PUT', body: scope }))
  const pending = loading.get(key)

  if (pending) { return pending }

  const request = ctx.rest<WorkspaceCatalog>('/workspaces', { owner }).then(catalog => {
    const current = $workspaces.get()[key]?.selected

    const topic = catalog.topics.find(t => t.id === current?.topic_id && t.business_id === current.business_id)
      || catalog.topics.find(t => t.id === catalog.selection?.topic_id && t.business_id === catalog.selection.business_id)
      || catalog.topics[0]

    const selected = topic && current?.topic_id === topic.id && current.business_id === topic.business_id ? current : topic ? { business_id: topic.business_id, topic_id: topic.id } : undefined
    $workspaces.set({ ...$workspaces.get(), [key]: { catalog, selected } })
  }).catch(error => {
    $workspaces.set({ ...$workspaces.get(), [key]: { ...$workspaces.get()[key], error: String(error) } })
  }).finally(() => { loading.delete(key) })

  loading.set(key, request)

  return request
}
