import { Button, type CronBlueprintOwner, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { type ReactNode, useEffect, useMemo } from 'react'

import { useWorkspaceRouting } from './workspace-routing'
import { $workspaces, loadWorkspaces, ownerKey, scopedContext, scopeKey, type WorkspaceState } from './workspace-state'

export function WorkspacePage({ ctx, children, owner: explicitOwner }: { ctx: PluginContext; children: (ctx: PluginContext) => ReactNode; owner?: CronBlueprintOwner }) {
  const active = useValue(host.state.requestOwner)
  const owner = explicitOwner || active
  const state = useValue($workspaces)[ownerKey(owner)]
  const route = useWorkspaceRouting(ctx, owner, state?.catalog)
  useEffect(() => { void loadWorkspaces(ctx, owner) }, [ctx, owner])
  const selected = state?.selected
  const scoped = useMemo(() => selected ? scopedContext(ctx, owner, selected) : null, [ctx, owner, selected])

  if (!selected || !scoped) {
    return <div className="p-4">{state?.error || '正在读取业务空间…'}{state?.error && <Button onClick={() => void loadWorkspaces(ctx, owner)}>重试</Button>}</div>
  }

  if (!route.ready) { return <p className="p-4">正在确认记录归属…</p> }

  if (route.error) { return <div className="space-y-2 p-4" role="alert">{route.error}{route.choices.map(choice => <Button key={choice.topic_id} onClick={() => route.pick(choice)}>{state?.catalog?.businesses.find(b => b.id === choice.business_id)?.name} / {state?.catalog?.topics.find(t => t.id === choice.topic_id)?.name}</Button>)}</div> }

  return <div className="flex h-full min-h-0 flex-col" key={scopeKey(owner, selected)}><ScopeHeader state={state} /><div className="min-h-0 flex-1 overflow-auto">{children(scoped)}</div></div>
}

function ScopeHeader({ state }: { state: WorkspaceState }) {
  const business = state.catalog?.businesses.find(item => item.id === state.selected?.business_id)
  const topic = state.catalog?.topics.find(item => item.id === state.selected?.topic_id)
  const status = business?.archived || topic?.archived ? '已归档 · 只读历史' : state.catalog?.paused ? '全部运营已暂停' : business?.paused ? '当前业务已暂停' : ''

  return <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b px-4 py-2 text-xs text-muted-foreground"><span>{business?.name} / {topic?.name}</span>{status && <span>{status}</span>}</header>
}
