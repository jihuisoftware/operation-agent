import { ContextMenu, ContextMenuContent, ContextMenuTrigger } from '@/components/ui/context-menu'
import { KbdGroup } from '@/components/ui/kbd'
import { SidebarMenuButton, SidebarMenuItem } from '@/components/ui/sidebar'
import { TipKeybindLabel } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { recordAction } from '@/store/desktop-metrics'
import { $newChatProfile } from '@/store/profile'
import { openRouteTile } from '@/store/route-tiles'

import type { AppView } from '../../routes'
import type { SidebarNavItem } from '../../types'
import { type NewSessionSplitHandler, startNewSessionDrag } from '../new-session-drag'

import { isSidebarNavActive } from './navigation'
import { NavigationTaskActivity } from './navigation-task-activity'
import { CONTEXT_SPLIT_KIT, SplitSubmenu } from './split-submenu'

interface Props {
  items: SidebarNavItem[]
  labels: Record<string, string>
  openInSplit: string
  currentView: AppView
  pathname: string
  onNavigate: (item: SidebarNavItem) => void
  onNewSessionSplit: NewSessionSplitHandler
  newSessionKbd: string[]
  newSessionKbdFlash: boolean
}

export function SidebarNavigation({
  items,
  labels,
  openInSplit,
  currentView,
  pathname,
  onNavigate,
  onNewSessionSplit,
  newSessionKbd,
  newSessionKbdFlash
}: Props) {
  return (
    <>
      {' '}
      {items.map(item => {
        const isInteractive = Boolean(item.action) || Boolean(item.route)

        const active = isSidebarNavActive(item, currentView, pathname)

        const isNewSession = item.id === 'new-session'

        const button = (
          <SidebarMenuButton
            aria-disabled={!isInteractive}
            className={cn(
              // no-drag: these rows sit directly under the titlebar's
              // [-webkit-app-region:drag] strips (app-shell.tsx), with only
              // 6px of clearance. Drag regions win hit-testing over DOM
              // (pointer-events can't override), and on Linux/WSLg the
              // resolved region has been observed to swallow clicks on the
              // top rows. Same carve-out as USER_BUBBLE_BASE_CLASS in
              // thread.tsx.
              'flex h-7 w-full justify-start gap-2 rounded-md border border-transparent px-2 text-left text-[0.8125rem] font-medium text-(--ui-text-secondary) transition-colors duration-100 ease-out [-webkit-app-region:no-drag] hover:bg-(--ui-control-hover-background) hover:text-foreground hover:transition-none',
              active &&
                'border-(--ui-stroke-tertiary) bg-(--ui-control-active-background) text-foreground shadow-none hover:border-(--ui-stroke-tertiary)!',
              !isInteractive && 'cursor-default hover:border-transparent hover:bg-transparent hover:text-inherit'
            )}
            // A tip anchored to the label points at the end of the
            // word; the row is what it's actually about.
            data-tip-region=""
            onClick={() => {
              // A plain new session lands in whatever profile the live
              // gateway is on (= the active switcher context). null →
              // no swap. The switcher header is the single place to
              // change which profile that is.
              if (isNewSession) {
                $newChatProfile.set(null)
              }

              if (item.keybindActionId) {
                recordAction(item.keybindActionId, 'click')
              }

              onNavigate(item)
            }}
            onPointerDown={event => {
              // The "New session" row is a drag source too: drag it onto
              // a chat zone's tab strip / edge / center to create the
              // session exactly there (stack / split). The pointer drag
              // session owns the gesture — a sub-threshold release falls
              // through to the onClick above (ordinary new session), and
              // an engaged drag suppresses that click so it never
              // double-creates. The create callback sets $newChatProfile
              // itself (the suppressed click can't), so a dragged new
              // session lands in the same profile a click would.
              if (!isNewSession) {
                return
              }

              startNewSessionDrag(placement => {
                $newChatProfile.set(null)
                onNewSessionSplit(placement.dir, { anchor: placement.anchor, before: placement.before })
              }, event)
            }}
            tooltip={
              item.keybindActionId
                ? {
                    children: (
                      <TipKeybindLabel
                        actionId={item.keybindActionId}
                        text={item.label || labels[item.id] || item.id}
                      />
                    )
                  }
                : item.label || labels[item.id] || item.id
            }
            type="button"
          >
            <item.icon className="size-4 shrink-0 text-[color-mix(in_srgb,currentColor_72%,transparent)]" />
            {/* Shrink-to-fit, not flex-1: the label carries the row's
                        `data-tour` handle, and anything anchored to it should
                        land at the end of the WORD, not out at the sidebar's
                        edge. Still truncates — `min-w-0` lets it shrink past
                        its content when the rail is narrow — and the trailing
                        chip's `ml-auto` was already doing the pushing that
                        `flex-1` looked like it was for.
                        Its own `sidebar-nav-` namespace: the overlay nav owns
                        `nav-<id>`, and both are on screen with Settings open. */}
            <span className="min-w-0 truncate" data-tip-arrow-only="" data-tour={`sidebar-nav-${item.id}`}>
              {item.label || labels[item.id] || item.id}
            </span>
            <NavigationTaskActivity item={item} label={item.label || labels[item.id] || item.id} />
            {isNewSession && (
              <KbdGroup
                className={cn('ml-auto opacity-55', newSessionKbdFlash && 'opacity-100!')}
                keys={newSessionKbd}
                size="sm"
              />
            )}
          </SidebarMenuButton>
        )

        // New session + route-backed pages can open in a split —
        // right-click for the directional "Open in split" submenu.
        return (
          <SidebarMenuItem key={item.id}>
            {isNewSession || item.route ? (
              <ContextMenu>
                <ContextMenuTrigger asChild>{button}</ContextMenuTrigger>
                <ContextMenuContent aria-label={item.label || labels[item.id] || item.id}>
                  <SplitSubmenu
                    kit={CONTEXT_SPLIT_KIT}
                    label={openInSplit}
                    onSplit={dir => {
                      if (isNewSession) {
                        onNewSessionSplit(dir)
                      } else if (item.route) {
                        openRouteTile(item.route, dir)
                      }
                    }}
                  />
                </ContextMenuContent>
              </ContextMenu>
            ) : (
              button
            )}
          </SidebarMenuItem>
        )
      })}
    </>
  )
}
