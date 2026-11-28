import { Badge, Button, type CronBlueprintOwner, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import {
  $loginNavigation,
  $loginRequest,
  $loginStatusRevision,
  $loginWorker,
  $loginWorkers,
  loginLabels,
  loginOwnerKey,
  type PlatformLogins,
  sameLoginOwner
} from './login-state'

interface PlatformLoginsProps {
  ctx: PluginContext
  owner: CronBlueprintOwner
}

export function PlatformLoginsPanel({ ctx, owner }: PlatformLoginsProps) {
  const current = useValue($loginWorker)
  const workers = useValue($loginWorkers)
  const navigating = useValue($loginNavigation)
  const revision = useValue($loginStatusRevision)

  const worker =
    workers[loginOwnerKey(owner)] || (current && sameLoginOwner(current.owner, owner) ? current.worker : null)

  const [data, setData] = useState<PlatformLogins | null>(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let disposed = false
    setData(null)

    const refresh = async () => {
      try {
        const next = await ctx.rest<PlatformLogins>(
          `/platforms${worker ? `?worker=${encodeURIComponent(worker)}` : ''}`,
          { owner }
        )

        if (!Array.isArray(next.platforms)) {
          throw new Error('请更新 Server 后重试')
        }

        if (!disposed) {
          setData(next)
          setError('')
        }
      } catch (error) {
        if (!disposed) {
          setData(null)
          setError(String(error))
        }
      }
    }

    void refresh()
    const timer = setInterval(() => void refresh(), 5000)

    return () => {
      disposed = true
      clearInterval(timer)
    }
  }, [ctx, owner, worker, retry, revision])

  const attention = data?.platforms.filter(
    p => p.state !== 'logged_in' || p.account_mismatch || p.observed_state === 'verification'
  ).length

  return (
    <section className="space-y-3 text-sm">
      <h2 className="font-medium">平台登录状态{data ? ` · ${attention} 个待检查或处理` : ''}</h2>
      <p className="text-xs text-muted-foreground">
        状态来自运营内嵌网页，按连接与 Profile
        隔离。已确认登录后持续保留，只有明确退出或失效才改为需要登录；任务执行前仍核对实际账号与权限。
      </p>
      {error && <p className="text-destructive">登录状态暂不可用：{error}</p>}
      {!data && !error && <p>正在读取登录状态…</p>}
      {data?.platforms.map(platform => (
        <div className="flex flex-wrap items-center gap-2 py-1" key={platform.id}>
          <span className="font-medium">{platform.name}</span>
          <Badge variant="muted">{loginLabels[platform.state]}</Badge>
          {platform.account_mismatch && <Badge variant="muted">账号与运营规则不匹配</Badge>}
          {platform.observed_state && platform.state !== platform.observed_state && (
            <span className="text-xs text-muted-foreground">最近检查结果：{loginLabels[platform.observed_state]}</span>
          )}
          {platform.confirmed_at && platform.state === 'logged_in' && (
            <span className="text-xs text-muted-foreground">
              登录确认：{new Date(platform.confirmed_at).toLocaleString('zh-CN')}
            </span>
          )}
          {platform.account_id && (
            <span className="text-xs text-muted-foreground">上次识别账号：{platform.account_id}</span>
          )}
          <span className="text-xs text-muted-foreground">
            {platform.checked_at
              ? `上次检查：${new Date(platform.checked_at).toLocaleString('zh-CN')}`
              : '尚无检查记录'}
          </span>
          <Button
            aria-label={`${platform.name}检查／登录`}
            disabled={Boolean(navigating)}
            onClick={() => {
              $loginRequest.set({ owner, platform: platform.id, url: platform.url, id: crypto.randomUUID() })
            }}
            size="sm"
            variant="outline"
          >
            检查／登录
          </Button>
          <p className="w-full text-xs text-muted-foreground">{platform.reason}</p>
        </div>
      ))}
      {data && !data.worker_online && (
        <p className="text-xs text-muted-foreground">
          当前 Profile 的桌面执行窗口未连接；授权请求会在窗口连接后打开，已保存的登录状态保留。
        </p>
      )}
      <div className="flex items-center gap-2">
        <Button onClick={() => setRetry(v => v + 1)} size="sm" variant="ghost">
          刷新状态
        </Button>
        <span className="text-xs text-muted-foreground">检查／登录会暂停自动动作；处理完成后到运营工作台恢复。</span>
      </div>
    </section>
  )
}
