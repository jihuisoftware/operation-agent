import type { Contribution } from '@/contrib/types'

// Sidebar-nav preferences — the `sidebarNav.prefs` registry area. A plugin
// (the sidebar manager) hides nav rows or re-orders them by CONTRIBUTING a
// preference; core still owns rendering and merges every contribution at
// render, so a preference only ever moves or drops a row that would otherwise
// render, and an id naming a row that does not exist is inert.
//
// Why a contribution and not a persisted `host.sidebar.hide()` store: the
// `host` singleton cannot tell which plugin wrote a preference, so a persisted
// write would outlive the plugin that made it (a hidden row with nothing left
// to restore it) and two plugins would overwrite each other's order. A
// contribution is attributed, merged with a stated rule, and dropped by the
// loader's per-plugin disposer on disable/reload — the rows come back on their
// own. The USER's choices persist in the plugin's own `ctx.storage`; the plugin
// re-contributes them on register.

export const SIDEBAR_NAV_PREFS_AREA = 'sidebarNav.prefs'

/** Payload (`data`) of a `sidebarNav.prefs` contribution. Ids are the nav rows'
 *  own ids: the core rows `'new-session' | 'capabilities' | 'messaging' |
 *  'artifacts' | 'cron'` (see `SidebarNavId`) or a `sidebar.nav` contribution's
 *  REGISTERED id — `ctx.register` namespaces it to `${pluginId}:${id}`. */
export interface SidebarNavPrefsContribution {
  /** Rows to drop. Merged as the UNION across contributions; `capabilities`
   *  (the row that hosts the Plugins tab) is never dropped. */
  hide?: string[]
  /** Secondary entries rendered below the primary workspace navigation. */
  footer?: string[]
  labels?: Record<string, string>
  /** Cold-start destination when no previous page or session exists. */
  home?: string
  /** Rows to place first, in this order. Contributions apply in the registry's
   *  area order (lowest `Contribution.order`, then registration); the first
   *  order wins, later ones place only ids not yet placed. */
  order?: string[]
}

/** Rows a preference may move but never hide: `capabilities` hosts the Plugins
 *  tab, the user's only path to a plugin's own off-switch. */
const NEVER_HIDDEN: ReadonlySet<string> = new Set(['capabilities'])

const cleanIds = (ids: unknown): string[] =>
  Array.isArray(ids) ? ids.filter((id): id is string => typeof id === 'string' && id.trim() !== '') : []

/** Apply every `sidebarNav.prefs` contribution to the nav rows, in the order
 *  given (the caller passes `registry.getArea`, so lowest `order` first, then
 *  registration). Pure so the arbitration is testable without a DOM:
 *  hidden = union of every `hide` minus `NEVER_HIDDEN` (hide beats order);
 *  `order` = first contribution first, later contributions place only ids not
 *  yet placed; rows no order names keep their default relative order after
 *  the named ones; unknown ids are inert. */
export function applySidebarNavPrefs<T extends { id: string; label?: string; placement?: 'main' | 'footer' }>(
  items: readonly T[],
  contributions: readonly Contribution[]
): T[] {
  const hidden = new Set<string>()
  const order: string[] = []

  for (const c of contributions) {
    const prefs = c.data as SidebarNavPrefsContribution | undefined

    cleanIds(prefs?.hide).forEach(id => {
      if (!NEVER_HIDDEN.has(id)) {
        hidden.add(id)
      }
    })
    order.push(...cleanIds(prefs?.order))
  }

  const byId = new Map(items.map(item => [item.id, item]))
  const placed = new Set<string>()
  const ordered: T[] = []

  for (const id of order) {
    const item = byId.get(id)

    if (item && !hidden.has(id) && !placed.has(id)) {
      ordered.push(item)
      placed.add(id)
    }
  }

  for (const item of items) {
    if (!hidden.has(item.id) && !placed.has(item.id)) {
      ordered.push(item)
    }
  }

  const footer = new Set(contributions.flatMap(c => cleanIds((c.data as SidebarNavPrefsContribution)?.footer)))

  const labels = Object.assign(
    {},
    ...contributions.map(c => (c.data as SidebarNavPrefsContribution)?.labels || {})
  ) as Record<string, string>

  return ordered.map(item =>
    !labels[item.id] && !footer.has(item.id)
      ? item
      : {
          ...item,
          ...(labels[item.id] ? { label: labels[item.id] } : {}),
          ...(footer.has(item.id) ? { placement: 'footer' as const } : {})
        }
  )
}

export function contributedHome(contributions: readonly Contribution[]): string | null {
  const home = contributions
    .map(c => (c.data as SidebarNavPrefsContribution)?.home)
    .find(path => path?.startsWith('/') && !path.startsWith('//'))

  return home || null
}
