import { BrowserReadinessError } from './browser-wait'

interface Operations {
  navigate: (url: string) => Promise<void>
  page: (operation: string) => Promise<any>
  ready: (phase: string) => Promise<unknown>
  clickLabel: (label: string) => Promise<unknown>
  locations: Record<string, string>
}

async function messages(operations: Operations) {
  const entry = await operations.page('open-messages')

  if (!entry.opened) { throw new BrowserReadinessError(entry.reason, 'CAPABILITY_UNAVAILABLE') }
}

export async function openInventory(payload: Record<string, any>, operations: Operations) {
  if (payload.kind === 'dm') { await messages(operations) } else { await operations.navigate(operations.locations[payload.kind]) }

  if (payload.kind === 'follow') { await operations.clickLabel('粉丝') }
  await operations.ready('inventory')
}

export async function openInteraction(payload: Record<string, any>, operations: Operations) {
  if (payload.kind === 'comment') {
    const url = payload.inventory_url ? new URL(payload.inventory_url) : null
    await operations.navigate(url?.hostname === 'www.xiaohongshu.com' && url.pathname === '/search_result' ? url.href : operations.locations.comment)
    await operations.ready('inventory')
    const opened = await operations.page('open-note')

    if (opened.opened !== payload.target) { throw new BrowserReadinessError(opened.reason, 'PAGE_NOT_READY') }
  } else if (payload.kind === 'dm') { await messages(operations) } else {
    await operations.navigate(operations.locations[payload.kind])

    if (payload.kind === 'follow') { await operations.clickLabel('粉丝') }
  }
}
