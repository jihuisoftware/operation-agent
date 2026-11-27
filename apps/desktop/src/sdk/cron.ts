import type { ReactNode } from 'react'

/** Profile-owned template libraries and plan summaries in the scheduler. */
export const CRON_BLUEPRINTS_AREA = 'cron.blueprints'
export interface CronBlueprintOwner {
  connectionId: string | null
  profile: string | null
}
export interface CronBlueprintContribution {
  planPath?: string
  render?: (props: { owner: CronBlueprintOwner; view: 'blueprints' | 'summary' }) => ReactNode
  /** Optional filtered business history inside the task history tab. */
  history?: { id: string; render: () => ReactNode }
  historyViews?: { id: string; label: string; render: () => ReactNode }[]
  renderExecution?: (props: { owner: CronBlueprintOwner; context: Record<string, unknown> }) => ReactNode
  renderToday?: () => ReactNode
  renderUpcoming?: (props: { owner: CronBlueprintOwner }) => ReactNode
}
