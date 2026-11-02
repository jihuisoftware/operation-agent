import type { CronBlueprintOwner } from '@hermes/plugin-sdk'
import { atom } from 'nanostores'

import type { BrowserCommand } from './types'

interface BrowserActivity { owner: CronBlueprintOwner; kind: BrowserCommand['kind'] }

export const $operationsBrowserActivity = atom<BrowserActivity | null>(null)
const activeOperations = new Set<BrowserActivity>()

export function beginBrowserActivity(owner: CronBlueprintOwner, kind: BrowserCommand['kind']) {
  const activity = { owner, kind }
  activeOperations.add(activity)
  $operationsBrowserActivity.set(activity)

  return () => {
    activeOperations.delete(activity)

    if ($operationsBrowserActivity.get() === activity) { $operationsBrowserActivity.set([...activeOperations].at(-1) || null) }
  }
}

export const $showOperationsBrowser = atom(false)
export const $operationsWorkerStatus = atom('等待连接')
