import { type CronBlueprintOwner, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'

import type { BlueprintCatalog, BlueprintPreview } from './blueprint-types'
import { withTopicDefaults } from './business-config'
import { initialPlan } from './plan-config'
import type { Policy } from './types'
import { $workspaceDirty, $workspaces, ownerKey, scopeKey, updateTopicName } from './workspace-state'

export function replacesSavedValue(change: BlueprintPreview['changes'][number]): boolean {
  if (['enabled', 'paused'].includes(change.field)) {
    return false
  }

  if (Array.isArray(change.before)) {
    return change.before.some(value => !(change.after as unknown[]).includes(value))
  }

  if (change.before && typeof change.before === 'object') {
    return Object.entries(change.before).some(([key, value]) =>
      replacesSavedValue({ field: key, before: value, after: (change.after as Record<string, unknown>)[key] })
    )
  }

  return Boolean(change.before) && change.before !== change.after
}

function planChanged(draft: Policy, saved: Policy) {
  return JSON.stringify(withTopicDefaults(draft)) !== JSON.stringify(withTopicDefaults(saved))
}

export function usePlanEditor(ctx: PluginContext, owner: CronBlueprintOwner) {
  const [catalog, setCatalog] = useState<BlueprintCatalog | null>(null)
  const [policy, setPolicy] = useState<Policy | null>(null)
  const [preview, setPreview] = useState<BlueprintPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [confirm, setConfirm] = useState(false)
  const retry = useRef<{ signature: string; id: string } | null>(null)
  const inFlight = useRef(false)
  const canSaveSettings = Boolean(catalog && policy && (catalog.version === 0 || planChanged(policy, catalog.policy)))

  const scope = useRef($workspaces.get()[ownerKey(owner)]?.selected).current
  const key = scope && scopeKey(owner, scope)
  const live = useRef(true)
  const edits = useRef({ plan: false, review: false })
  const markDirty = (part: 'plan' | 'review', dirty: boolean) => {
    edits.current[part] = dirty
    if (key && live.current) $workspaceDirty.set({ ...$workspaceDirty.get(), [key]: edits.current.plan || edits.current.review })
  }
  useEffect(() => {
    live.current = true
    return () => {
      live.current = false
      if (key) $workspaceDirty.set({ ...$workspaceDirty.get(), [key]: false })
    }
  }, [key])
  useEffect(() => {
    let disposed = false
    void ctx
      .rest<BlueprintCatalog>('/blueprints')
      .then(value => {
        if (!disposed) {
          setCatalog(value)
          setPolicy(initialPlan(value))
        }
      })
      .catch(reason => {
        if (!disposed) {
          setError(String(reason))
        }
      })

    return () => {
      disposed = true
    }
  }, [ctx])
  useEffect(() => {
    if (!policy || !catalog) {
      return
    }

    let disposed = false

    const timer = setTimeout(
      () =>
        void ctx
          .rest<BlueprintPreview>('/blueprints/preview', {
            method: 'POST',
            body: { version: catalog.version, policy: withTopicDefaults(policy) }
          })
          .then(value => {
            if (!disposed) {
              setPreview(value)
              setError('')
            }
          })
          .catch(reason => {
            if (!disposed) {
              setPreview(null)
              setError(String(reason))
            }
          }),
      250
    )

    return () => {
      disposed = true
      clearTimeout(timer)
    }
  }, [ctx, policy, catalog])

  const change = (next: Policy) => {
    if (!catalog || inFlight.current) return
    markDirty('plan', planChanged(next, catalog.policy))
    setPolicy(next)
    setNotice('')
    setPreview(null)
    setConfirm(false)
  }

  const save = async (start: boolean) => {
    if (!policy || !catalog || !preview || inFlight.current || (!start && !canSaveSettings)) {
      return
    }

    if (catalog.version > 0 && preview.changes.some(replacesSavedValue) && !confirm) {
      setConfirm(true)

      return
    }

    const payload = { version: catalog.version, policy: withTopicDefaults(policy), start }
    const signature = JSON.stringify(payload)
    if (retry.current?.signature !== signature) {
      retry.current = { signature, id: crypto.randomUUID() }
    }

    inFlight.current = true
    setBusy(true)
    setError('')

    try {
      await ctx.rest('/quick-start', {
        method: 'POST',
        body: { ...payload, request_id: retry.current.id }
      })
      const current = await ctx.rest<BlueprintCatalog>('/blueprints')
      retry.current = null
      setPreview(null)
      setCatalog(current)
      setPolicy(current.policy)
      markDirty('plan', false)
      if (scope) updateTopicName(owner, scope, current.policy.topic)
      setConfirm(false)
      setNotice(start ? '首轮已安排，可在任务与历史查看执行结果。' : '已保存，可继续补充详细设置。')
    } catch (reason) {
      setError(String(reason))
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  const control = async (action: string) => {
    if (!catalog || inFlight.current) {
      return
    }

    inFlight.current = true
    setBusy(true)

    try {
      await ctx.rest('/plan/control', { method: 'POST', body: { action, version: catalog.version } })
      const current = await ctx.rest<BlueprintCatalog>('/blueprints')
      setCatalog(current)
      setPolicy(draft =>
        draft && planChanged(draft, catalog.policy)
          ? { ...draft, enabled: current.policy.enabled, paused: current.policy.paused }
          : current.policy
      )
      setNotice(action === 'run' ? '已安排手动执行，忽略原排期；可在任务与历史查看。' : '计划状态已更新')
    } catch (reason) {
      setError(String(reason))
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  const reviewChanged = (dirty: boolean) => markDirty('review', dirty)
  return { canSaveSettings, reviewChanged, catalog, policy, preview, busy, error, notice, confirm, change, save, control }
}
