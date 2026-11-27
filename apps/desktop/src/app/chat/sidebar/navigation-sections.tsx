import { useStore } from '@nanostores/react'
import { useMemo } from 'react'

import { SIDEBAR_NAV_AREA } from '@/app/routes'
import { useContributions } from '@/contrib/react/use-contributions'
import { $interfaceMode, shownInMode } from '@/store/interface-mode'
import { applySidebarNavPrefs, SIDEBAR_NAV_PREFS_AREA } from '@/store/sidebar-nav'
import { Codicon } from '@/components/ui/codicon'
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { SidebarGroup, SidebarGroupContent, SidebarMenu, SidebarMenuButton, SidebarMenuItem } from '@/components/ui/sidebar'

import { contributedSidebarNavItem, isSidebarNavActive, SIDEBAR_NAV } from './navigation'
import { SidebarNavigation, type SidebarNavigationProps } from './navigation-rows'

export function useSidebarNavigationItems() {
  const contributions = useContributions(SIDEBAR_NAV_AREA)
  const preferences = useContributions(SIDEBAR_NAV_PREFS_AREA)
  const mode = useStore($interfaceMode)
  return useMemo(() => {
    const items = [...SIDEBAR_NAV, ...contributions.flatMap(contributedSidebarNavItem)]
    return applySidebarNavPrefs(items.filter(shownInMode(mode)), preferences)
  }, [contributions, mode, preferences])
}

export function SidebarMainNavigation(props: SidebarNavigationProps) {
  const primary = props.items.filter(item => (item.placement ?? 'main') === 'main')
  return <SidebarGroup className="shrink-0 p-0 pb-2">
    <SidebarGroupContent><SidebarMenu className="gap-px"><SidebarNavigation {...props} items={primary} /></SidebarMenu></SidebarGroupContent>
  </SidebarGroup>
}

export function SidebarFooterNavigation(props: SidebarNavigationProps) {
  const shortcuts = props.items.filter(item => item.placement === 'footer')
  const more = props.items.filter(item => item.placement === 'more')

  if (!more.length) return <SidebarMenu className="shrink-0 gap-px pb-2"><SidebarNavigation {...props} items={shortcuts} /></SidebarMenu>

  return <SidebarMenu className="@container/footer shrink-0 flex-row items-center gap-px pb-2">
    <SidebarNavigation {...props} items={shortcuts} layout="compact" />
    <SidebarMenuItem className="min-w-0 flex-auto">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <SidebarMenuButton className="h-7 justify-center gap-1 px-1 text-xs" isActive={more.some(item => isSidebarNavActive(item, props.currentView, props.pathname))}>
            <Codicon className="size-4 @max-[200px]/footer:hidden" name="ellipsis" />更多
          </SidebarMenuButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" aria-label="更多" side="top">
          <SidebarMenu className="gap-px"><SidebarNavigation {...props} items={more} layout="menu" /></SidebarMenu>
        </DropdownMenuContent>
      </DropdownMenu>
    </SidebarMenuItem>
  </SidebarMenu>
}
