import { type CronBlueprintOwner, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import type { PlanTime } from './blueprint-types'
import { $loginStatusRevision, type PlatformLogin } from './login-state'

export interface OverviewData {
  day: string
  timezone: string
  updated_at: string
  version: number
  topic: string
  goal: string
  enabled: boolean
  paused: boolean
  online: boolean
  counts: { sources: number; sources_read: number; content: number; topics: number; published: number; interactions: number; model_calls: number }
  pending: { unverified: number; failed_today: number; inbox: number; content: number }
  runs: { id: string; stage: string; state: string; detail: string; started: string; ended: string | null }[]
  publications: { id: string; created: string; state: string; title: string | null; account_id: string | null; url: string | null }[]
  report: { id: string; created: string; day: string } | null
  schedule: PlanTime[]
  analysis?: { id: string; kind: string; created: string; detail: string }[]
  platforms: PlatformLogin[]
  platform_worker_online?: boolean
}

export function useOverview(ctx: PluginContext, owner: CronBlueprintOwner) {
  const [data, setData] = useState<OverviewData | null>(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const loginRevision = useValue($loginStatusRevision)
  useEffect(() => {
    let disposed = false
    let busy = false

    const refresh = async () => {
      if (busy) { return }
      busy = true

      try {
        const next = await ctx.rest<OverviewData>('/overview', { owner, timeoutMs: 10000 })

        if (!disposed) { setData(next); setError('') }
      } catch (error) {
        if (!disposed) { setError(String(error)) }
      } finally {
        busy = false
      }
    }

    const visibleRefresh = () => { if (!document.hidden) { void refresh() } }
    void refresh()
    const timer = setInterval(visibleRefresh, 5000)
    document.addEventListener('visibilitychange', visibleRefresh)

    return () => {
      disposed = true
      clearInterval(timer)
      document.removeEventListener('visibilitychange', visibleRefresh)
    }
  }, [ctx, owner, revision, loginRevision])

  return { data, error, retry: () => setRevision(value => value + 1) }
}
