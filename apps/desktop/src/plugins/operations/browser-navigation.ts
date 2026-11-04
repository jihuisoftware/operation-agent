import { BrowserReadinessError, waitForRead } from './browser-wait'
import type { Guest } from './types'

/** The webview IPC promise acknowledges dispatch, not completion of navigation. */
export async function navigateGuest(guest: Guest, url: string, sleep?: (ms: number) => Promise<unknown>) {
  const before = guest.getURL()

  if (before === url) { return }
  let loaded = false
  let failure: Error | undefined

  const stopped = () => { loaded = guest.getURL() !== before }

  const failed = (event: Event) => {
    const detail = event as Event & { errorCode: number; errorDescription: string; isMainFrame: boolean }

    if (detail.isMainFrame && detail.errorCode !== -3) { failure = new BrowserReadinessError(`网页加载失败：${detail.errorDescription}`, 'PAGE_UNAVAILABLE') }
  }

  guest.addEventListener('did-stop-loading', stopped)
  guest.addEventListener('did-fail-load', failed)

  try {
    await guest.loadURL(url)
    await waitForRead(async () => loaded || Boolean(failure), Boolean, 60000, false, sleep)

    if (failure) { throw failure }
  } finally {
    guest.removeEventListener('did-stop-loading', stopped)
    guest.removeEventListener('did-fail-load', failed)
  }
}
