import { type CronBlueprintOwner, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'

import { bindScopeRoute, chooseScope, ownerKey, type WorkspaceCatalog } from './workspace-state'

export function useWorkspaceRouting(ctx: PluginContext, owner: CronBlueprintOwner, catalog?: WorkspaceCatalog) {
  const [params, setParams] = useSearchParams()
  const query = params.toString()
  const key = ownerKey(owner) + ':' + query
  const [resolved, setResolved] = useState<{ key: string; error?: string } | null>(null)
  const loaded = Boolean(catalog)
  const [previousOwner, setPreviousOwner] = useState(ownerKey(owner))
  const changedOwner = previousOwner !== ownerKey(owner)
  useEffect(() => {
    if (!changedOwner) { return }
    setPreviousOwner(ownerKey(owner))
    setParams(previous => {
      const next = new URLSearchParams(previous)

      for (const field of ['business_id', 'topic_id', 'record', 'selected', 'action', 'draft', 'new', 'from_content']) { next.delete(field) }

      return next
    }, { replace: true })
  }, [changedOwner, owner, setParams])
  useEffect(() => bindScopeRoute(owner, scope => {
    setParams(previous => {
      const next = new URLSearchParams(previous)
      next.set('business_id', scope.business_id); next.set('topic_id', scope.topic_id)

      for (const field of ['record', 'selected', 'action', 'draft', 'new', 'from_content']) { next.delete(field) }

      return next
    }, { replace: true })
  }), [owner, setParams])
  useEffect(() => {
    if (!loaded || changedOwner) { return }
    let disposed = false

    const resolve = async () => {
      const values = new URLSearchParams(query)
      const business = values.get('business_id'), topic = values.get('topic_id')

      if (business || topic) {
        // The server is authoritative; do not default a malformed link to another scope.
        if (!business || !topic) { throw new Error('链接缺少业务或主题归属') }
        await ctx.rest('/policy?' + new URLSearchParams({ business_id: business, topic_id: topic }), { owner })

        if (!disposed) { chooseScope(owner, { business_id: business, topic_id: topic }, false) }
      }

      if (!disposed) { setResolved({ key }) }
    }

    void resolve().catch(reason => { if (!disposed) { setResolved({ key, error: String(reason) }) } })

    return () => { disposed = true }
  }, [ctx, owner, query, key, loaded, changedOwner, setParams])

  return { ready: resolved?.key === key, error: resolved?.key === key ? resolved.error : '' }
}
