import type { CronBlueprintOwner } from '@hermes/plugin-sdk'
import { type RefObject, useCallback, useEffect, useState } from 'react'

import type { Guest } from './types'

export const OPERATIONS_HOME = 'https://www.xiaohongshu.com/explore'

/** Cookie ownership is stable across renderer/API reconnects; visibility is not lifecycle. */
export function useOperationsGuest(owner: CronBlueprintOwner & { account_id?: string }, container: RefObject<HTMLDivElement | null>, home = OPERATIONS_HOME) {
  const [guest, setGuest] = useState(() => document.createElement('webview') as Guest)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const replace = useCallback(() => { setGuest(document.createElement('webview') as Guest) }, [])

  useEffect(() => {
    let disposed = false

    const start = () => { setLoading(true); setError('') }

    const ready = () => { setLoading(false) }

    const failed = (event: Event) => {
      const detail = event as Event & { isMainFrame: boolean; errorCode: number; errorDescription: string }

      if (!detail.isMainFrame || detail.errorCode === -3) { return }
      setLoading(false)
      setError(`网页加载失败：${detail.errorDescription}`)
    }

    const crashed = () => { setLoading(false); setError('网页进程已退出，请重新打开网页；已保存的登录数据仍保留。') }
    guest.addEventListener('did-start-loading', start)
    guest.addEventListener('dom-ready', ready)
    guest.addEventListener('did-stop-loading', ready)
    guest.addEventListener('did-navigate-in-page', ready)
    guest.addEventListener('did-fail-load', failed)
    guest.addEventListener('render-process-gone', crashed)
    guest.setAttribute('webpreferences', 'contextIsolation=yes,sandbox=yes,nodeIntegration=no,backgroundThrottling=no')
    guest.style.cssText = 'width:100%;height:100%;display:flex'
    // Preserve the deployed partition format/order so existing logins remain available.
    const identity = JSON.stringify({ profile: owner.profile, connectionId: owner.connectionId, account: owner.account_id })
    void crypto.subtle.digest('SHA-256', new TextEncoder().encode(identity)).then(buffer => {
      if (disposed) { return }
      const key = Array.from(new Uint8Array(buffer), byte => byte.toString(16).padStart(2, '0')).join('')
      guest.setAttribute('partition', `persist:operations-${key}`)
      guest.setAttribute('src', home)
      container.current?.append(guest)
    }).catch(reason => {
      if (!disposed) { setLoading(false); setError(`无法恢复网页：${String(reason)}`) }
    })

    return () => {
      disposed = true
      guest.removeEventListener('did-start-loading', start)
      guest.removeEventListener('dom-ready', ready)
      guest.removeEventListener('did-stop-loading', ready)
      guest.removeEventListener('did-navigate-in-page', ready)
      guest.removeEventListener('did-fail-load', failed)
      guest.removeEventListener('render-process-gone', crashed)
      guest.remove()
    }
  }, [guest, owner.profile, owner.connectionId, owner.account_id, container, home])

  const reopen = async () => {
    setError('')
    setLoading(true)

    try { await guest.loadURL(home) } catch (reason) {
      setLoading(false)
      setError(`无法打开网页：${String(reason)}`)
    }
  }

  return { guest, loading, error, reopen, replace }
}
