import { Badge, Button, Codicon, formatTimestamp, host } from '@hermes/plugin-sdk'
import type { ReactNode } from 'react'

export const overviewRoutes = {
  rules: '/cron?tab=plan',
  content: '/content?tab=drafts',
  tasks: '/cron?tab=history',
  sources: '/materials?tab=sources',
  topics: '/content?tab=topics',
  reports: '/overview?tab=reports'
}

export function Open({ to, children, label }: { to: string; children: ReactNode; label?: string }) {
  return (
    <Button aria-label={label} onClick={() => host.navigate(to)} variant="ghost">
      {children}
    </Button>
  )
}

export function Time({ value }: { value: string }) {
  return (
    <time dateTime={value} title={value}>
      {formatTimestamp(value)}
    </time>
  )
}

export function Region({
  title,
  icon,
  to,
  children
}: {
  title: string
  icon: string
  to: string
  children: ReactNode
}) {
  return (
    <section aria-label={title} className="min-w-0 space-y-4 rounded-lg bg-muted/30 p-4">
      <header className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 font-semibold">
          <Codicon className="text-primary" name={icon} />
          {title}
        </h2>
        <Open label={`查看${title}详情`} to={to}>
          查看
          <Codicon name="chevron-right" />
        </Open>
      </header>
      {children}
    </section>
  )
}

export function Empty({ icon, children }: { icon: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-3 py-4 text-muted-foreground">
      <Codicon className="opacity-60" name={icon} size={24} />
      <p className="text-xs">{children}</p>
    </div>
  )
}

const states: Record<string, string> = {
  running: '执行中',
  completed: '完成',
  failed: '失败',
  skipped: '跳过',
  cancelled: '已取消',
  pending: '等待执行',
  blocked: '受阻',
  needs_attention: '待处理',
  queued: '排队中',
  interrupted: '已中断',
  unknown: '待核对',
  paused: '已暂停'
}

export function RunState({ state }: { state: string }) {
  const icons: Record<string, string> = {
    completed: 'pass',
    running: 'loading',
    failed: 'error',
    needs_attention: 'warning'
  }

  const variant =
    state === 'completed' ? 'success' : state === 'failed' ? 'destructive' : state === 'running' ? 'default' : 'muted'

  return (
    <Badge variant={variant}>
      <Codicon name={icons[state] || 'circle-outline'} spinning={state === 'running'} />
      {states[state] || state}
    </Badge>
  )
}
