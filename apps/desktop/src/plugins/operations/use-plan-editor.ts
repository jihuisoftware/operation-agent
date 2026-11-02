import type { PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'

import type { BlueprintCatalog, BlueprintPreview } from './blueprint-types'
import { withTopicDefaults } from './business-config'
import { initialPlan } from './plan-config'
import type { Policy } from './types'

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

export function usePlanEditor(ctx: PluginContext) {
  const [catalog, setCatalog] = useState<BlueprintCatalog | null>(null)
  const [policy, setPolicy] = useState<Policy | null>(null)
  const [preview, setPreview] = useState<BlueprintPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [confirm, setConfirm] = useState(false)
  const request = useRef({ id: crypto.randomUUID(), start: false })
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
    setPolicy(next)
    setNotice('')
    setPreview(null)
    setConfirm(false)
    request.current = { id: crypto.randomUUID(), start: false }
  }

  const save = async (start: boolean) => {
    if (!policy || !catalog || !preview || busy) {
      return
    }

    if (catalog.version > 0 && preview.changes.some(replacesSavedValue) && !confirm) {
      setConfirm(true)

      return
    }

    if (request.current.start !== start) {
      request.current = { id: crypto.randomUUID(), start }
    }

    setBusy(true)
    setError('')

    try {
      await ctx.rest('/quick-start', {
        method: 'POST',
        body: { request_id: request.current.id, version: catalog.version, policy: withTopicDefaults(policy), start }
      })
      const current = await ctx.rest<BlueprintCatalog>('/blueprints')
      setCatalog(current)
      setPolicy(current.policy)
      setConfirm(false)
      setNotice(start ? '首轮已安排，下方持续显示执行结果。' : '已保存，可继续补充详细设置。')
    } catch (reason) {
      setError(String(reason))
    } finally {
      setBusy(false)
    }
  }

  const control = async (action: string) => {
    if (!catalog || busy) {
      return
    }

    setBusy(true)

    try {
      await ctx.rest('/plan/control', { method: 'POST', body: { action, version: catalog.version } })
      const current = await ctx.rest<BlueprintCatalog>('/blueprints')
      setCatalog(current)
      setPolicy(draft =>
        draft && JSON.stringify(draft) !== JSON.stringify(catalog.policy)
          ? { ...draft, enabled: current.policy.enabled, paused: current.policy.paused }
          : current.policy
      )
      setNotice(action === 'run' ? '已安排手动执行，忽略原排期；可在任务与历史查看。' : '计划状态已更新')
    } catch (reason) {
      setError(String(reason))
    } finally {
      setBusy(false)
    }
  }

  return { catalog, policy, preview, busy, error, notice, confirm, change, save, control }
}
