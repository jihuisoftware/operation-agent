import { useStore } from '@nanostores/react'
import { computed, type ReadableAtom } from 'nanostores'
import { useMemo } from 'react'

import { SIDEBAR_NAV_AREA, type SidebarNavContribution } from '@/app/routes'
import type { SidebarNavItem } from '@/app/types'
import { Codicon } from '@/components/ui/codicon'
import { GlyphSpinner } from '@/components/ui/glyph-spinner'
import { useContributions } from '@/contrib/react/use-contributions'
import { $agentTaskActivity, $cronTaskActivity } from '@/store/navigation-activity'
import type { TaskActivity } from '@/store/task-activity'

export function NavigationTaskActivity({ item, label }: { item: SidebarNavItem; label: string }) {
  if (item.id === 'activity') { return <SystemTaskActivity /> }
  const source = item.activity ?? ({ cron: $cronTaskActivity, 'new-session': $agentTaskActivity } as Record<string, ReadableAtom<TaskActivity>>)[item.id]

  return source ? <TaskActivityBadge activity={source} label={label} /> : null
}

function SystemTaskActivity() {
  const contributions = useContributions(SIDEBAR_NAV_AREA)

  const activity = useMemo(() => {
    const sources = contributions.flatMap(item => {
      const source = (item.data as SidebarNavContribution | undefined)?.activity

      return source ? [source] : []
    })

    return computed([$cronTaskActivity, $agentTaskActivity, ...sources], (...states) => ({
      running: states.some(state => state.running > 0) ? 1 : 0,
      unavailable: states.some(state => state.unavailable)
    }))
  }, [contributions])

  return <TaskActivityBadge activity={activity} label="系统" summary />
}

export function TaskActivityBadge({ activity, label, summary = false }: {
  activity: ReadableAtom<TaskActivity>
  label: string
  summary?: boolean
}) {
  const { running, unavailable } = useStore(activity)

  const message = running > 0
    ? `${label}：${summary ? '有任务' : `${running} 项任务`}正在执行${unavailable ? '，部分状态暂不可用' : ''}`
    : `${label}：执行状态暂不可用，重新聚焦窗口后重试`

  if (!running && !unavailable) { return null }

  return <span className="ml-auto inline-flex shrink-0 items-center gap-1 text-xs text-muted-foreground" title={message}>
    {running > 0
      ? <><GlyphSpinner ariaLabel={message} className="size-3" />{!summary && <span aria-hidden="true">{running}</span>}</>
      : <Codicon aria-label={message} className="size-3" name="warning" />}
  </span>
}
