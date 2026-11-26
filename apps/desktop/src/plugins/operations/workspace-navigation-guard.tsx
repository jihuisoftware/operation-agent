import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  host,
  useValue
} from '@hermes/plugin-sdk'
import { useEffect } from 'react'

import { $pendingLeave, dirtyScope, discardAndContinue, guardWorkspaceChange } from './workspace-navigation'
import { ownerKey } from './workspace-state'

export function WorkspaceNavigationGuard() {
  const owner = useValue(host.state.requestOwner)
  const pending = useValue($pendingLeave)
  useEffect(() => {
    $pendingLeave.set(null)
    const navigation = window.navigation
    let rollback = false
    const guard = (event: NavigateEvent) => {
      if (rollback || !event.destination.sameDocument || !dirtyScope(owner)) return
      const url = event.destination.url
      if (new URL(url).hash === window.location.hash) return
      const key = event.destination.key
      if (event.navigationType === 'traverse') {
        // Restore the previous entry before the HashRouter sees the pop. This
        // preserves both the mounted editor and the browser's back/forward list.
        const original = navigation.currentEntry?.key
        if (!original) return
        rollback = true
        const restore = (pop: PopStateEvent) => {
          pop.stopImmediatePropagation()
          void Promise.resolve(navigation.traverseTo(original).finished).then(
            () => {
              rollback = false
              guardWorkspaceChange(owner, () => {
                void navigation.traverseTo(key)
              })
            },
            () => {
              rollback = false
            }
          )
        }
        window.addEventListener('popstate', restore, { capture: true, once: true })
        return
      }
      if (!event.cancelable) return
      event.preventDefault()
      guardWorkspaceChange(owner, () => {
        if (event.navigationType === 'replace') window.location.replace(url)
        else host.navigate(new URL(url).hash)
      })
    }
    const unload = (event: BeforeUnloadEvent) => {
      if (dirtyScope(owner)) event.preventDefault()
    }
    navigation?.addEventListener('navigate', guard)
    window.addEventListener('beforeunload', unload)
    return () => {
      navigation?.removeEventListener('navigate', guard)
      window.removeEventListener('beforeunload', unload)
    }
  }, [owner])
  return (
    <Dialog
      open={pending?.owner === ownerKey(owner)}
      onOpenChange={open => {
        if (!open) $pendingLeave.set(null)
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>放弃当前计划的修改？</DialogTitle>
          <DialogDescription>当前主题有未保存的设置。</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button onClick={() => $pendingLeave.set(null)} variant="outline">
            继续编辑
          </Button>
          <Button onClick={discardAndContinue}>放弃修改并切换</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
