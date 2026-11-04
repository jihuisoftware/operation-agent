import { waitForDocument } from './browser-document'
import { type BrowserExecution, evidenceDeadline } from './browser-execution'
import { PAGE_LOAD_MS } from './browser-timeouts'
import { BrowserReadinessError, waitForRead } from './browser-wait'
import type { Guest } from './types'

function matchesDocument(actual: string, target: URL) {
  if (!actual) { return false }
  const current = new URL(actual)

  if (current.origin !== target.origin) { return false }

  // A same-origin login/error redirect must reach the login inspector, not masquerade as a load timeout.
  if (/^\/(login|404)(\/|$)/.test(current.pathname)) { return true }

  return current.pathname.replace(/\/$/, '') === target.pathname.replace(/\/$/, '') &&
    [...target.searchParams].every(([key, value]) => current.searchParams.getAll(key).includes(value))
}

/** A visible DOM can still be loading: Electron queues executeJavaScript until the main frame finishes. */
export async function navigateGuest(guest: Guest, url: string, sleep?: (ms: number) => Promise<unknown>, execution?: BrowserExecution) {
  const target = new URL(url)
  const samePage = guest.getURL() === target.href

  if (samePage && !guest.isLoadingMainFrame?.()) { return }
  let loaded = false
  let failure: Error | undefined

  const ready = (event?: Event) => {
    if ((event as Event & { isMainFrame?: boolean } | undefined)?.isMainFrame === false) { return }
    loaded = matchesDocument(guest.getURL(), target)
  }

  const failed = (event: Event) => {
    const detail = event as Event & { errorCode: number; errorDescription: string; isMainFrame: boolean }

    if (detail.isMainFrame && detail.errorCode !== -3) { failure = new BrowserReadinessError(`网页加载失败：${detail.errorDescription}`, 'PAGE_UNAVAILABLE') }
  }

  const events = ['dom-ready', 'did-navigate-in-page', 'did-stop-loading']

  for (const name of events) { guest.addEventListener(name, ready) }
  guest.addEventListener('did-fail-load', failed)

  try {
    const navigate = async () => {
      execution?.assert()

      if (samePage) {
        loaded = matchesDocument(guest.getURL(), target)
      } else {
        void guest.loadURL(target.href).catch((reason: Error & { code?: string; errno?: number }) => {
          if (reason.code !== 'ERR_ABORTED' && reason.errno !== -3) {
            failure = new BrowserReadinessError(`网页导航失败：${reason.message}`, 'PAGE_UNAVAILABLE')
          }
        })
      }

      await waitForRead(async () => loaded || Boolean(failure), Boolean, PAGE_LOAD_MS, false, sleep, execution)

      if (!failure) {
        if (execution) { await waitForDocument(guest, execution, sleep) } else {
          await waitForRead(async () => !guest.isLoadingMainFrame?.(), Boolean, PAGE_LOAD_MS, false, sleep)
        }
      }
    }

    if (execution) { await execution.loading(navigate, PAGE_LOAD_MS, `页面加载（${target.pathname}）`) } else { await evidenceDeadline(navigate, Date.now() / 1000 + PAGE_LOAD_MS / 1000, PAGE_LOAD_MS) }

    if (failure) { throw failure }
  } finally {
    for (const name of events) { guest.removeEventListener(name, ready) }
    guest.removeEventListener('did-fail-load', failed)
  }
}
