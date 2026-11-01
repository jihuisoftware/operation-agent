import { Codicon } from '@/components/ui/codicon'
import type { Contribution } from '@/contrib/types'

import { type AppView, ARTIFACTS_ROUTE, CAPABILITIES_ROUTE, CRON_ROUTE, type SidebarNavContribution } from '../../routes'
import type { SidebarNavItem } from '../../types'

export function contributedSidebarNavItem(contribution: Contribution): SidebarNavItem[] {
  const data = contribution.data as Partial<SidebarNavContribution> | undefined

  if (!data?.path?.startsWith('/') || !data.label) { return [] }
  const codicon = data.codicon || 'plug'

  return [{
    id: contribution.id,
    label: data.label,
    icon: props => <Codicon name={codicon} {...props} />,
    route: data.path,
    tier: data.tier,
    activity: data.activity
  }]
}

// A row's `tier` is the one mode it belongs to (Simple keeps the setup rows,
// Advanced adds the readouts); the list filters once, nothing is passed down.
export const SIDEBAR_NAV: SidebarNavItem[] = [
  {
    id: 'new-session',
    label: '',
    icon: props => <Codicon name="robot" {...props} />,
    action: 'new-session',
    keybindActionId: 'session.new'
  },
  {
    id: 'cron',
    label: '',
    icon: props => <Codicon name="watch" {...props} />,
    route: CRON_ROUTE,
    keybindActionId: 'nav.cron'
  },
  {
    id: 'activity', label: '实时状态', icon: props => <Codicon name="pulse" {...props} />, route: '/activity'
  },
  {
    id: 'upcoming', label: '待执行任务', icon: props => <Codicon name="checklist" {...props} />, route: '/upcoming'
  },
  {
    id: 'capabilities',
    label: '',
    icon: props => <Codicon name="symbol-misc" {...props} />,
    route: CAPABILITIES_ROUTE,
    keybindActionId: 'nav.capabilities'
  },

  // Content outputs and scheduled work stay reachable in the operations Simple mode.
  {
    id: 'artifacts',
    label: '',
    icon: props => <Codicon name="files" {...props} />,
    route: ARTIFACTS_ROUTE,
    keybindActionId: 'nav.artifacts'
  }
]


export function isSidebarNavActive(item: SidebarNavItem, view: AppView, pathname: string): boolean {
  const builtin = ['capabilities', 'artifacts', 'cron', 'activity', 'upcoming'].includes(item.id)

  return (builtin && item.id === view) || (view === 'extension' && item.route === pathname)
}
