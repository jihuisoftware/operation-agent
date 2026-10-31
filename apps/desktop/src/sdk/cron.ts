import type { ReactNode } from 'react'

/** Profile-owned template libraries and plan summaries in the scheduler. */
export const CRON_BLUEPRINTS_AREA = 'cron.blueprints'
export interface CronBlueprintOwner {
  connectionId: string | null
  profile: string | null
}
export interface CronBlueprintContribution {
  render: (props: { owner: CronBlueprintOwner; view: 'blueprints' | 'summary' }) => ReactNode
}
