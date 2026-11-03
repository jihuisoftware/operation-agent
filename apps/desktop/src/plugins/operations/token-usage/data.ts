import type { PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

export const periods: Record<string, string> = { live: '实时', hour: '最近一小时', day: '当天', week: '最近一周', month: '最近一个月' }
export const dimensions: Record<string, string> = { business: '业务', topic: '主题', module: '功能模块', model: '模型', provider: '提供方', purpose: '调用用途' }
export const statuses: Record<string, string> = { running: '统计中', confirmed: '已确认', completed: '完成', failed: '失败', unknown: '用量未知', interrupted: '已中断', cancelled: '已取消', skipped: '跳过', partial: '部分完成' }
export const number = (value: number | null | undefined) => value == null ? '未知' : value.toLocaleString('zh-CN')
export const timestamp = (value: number) => new Date(value * 1000).toISOString()
export const queryString = (period: string, filters: Record<string, string> = {}) => new URLSearchParams({
  period, tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
  ...Object.fromEntries(Object.entries(filters).filter(([, value]) => value).map(([key, value]) => [`filter_${key}`, value]))
}).toString()

export function useUsage<T>(ctx: PluginContext, path: string) {
  const [state, setState] = useState<{ path: string; ctx: PluginContext; data?: T; error?: string }>()
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let disposed = false
    let busy = false

    const refresh = async () => {
      if (busy || document.hidden) { return }
      busy = true

      try {
        const data = await ctx.rest<T>(path)

        if (!disposed) { setState({ path, ctx, data }) }
      } catch (reason) {
        if (!disposed) { setState(old => ({ path, ctx, data: old?.path === path && old.ctx === ctx ? old.data : undefined, error: String(reason) })) }
      } finally { busy = false }
    }

    void refresh()
    const timer = setInterval(() => void refresh(), 5000)
    document.addEventListener('visibilitychange', refresh)

    return () => { disposed = true; clearInterval(timer); document.removeEventListener('visibilitychange', refresh) }
  }, [ctx, path, revision])
  const current = state?.path === path && state.ctx === ctx ? state : undefined

  return { data: current?.data, error: current?.error, retry: () => setRevision(value => value + 1) }
}
