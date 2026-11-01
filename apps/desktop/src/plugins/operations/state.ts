import type { CronBlueprintOwner } from '@hermes/plugin-sdk'
import { atom } from 'nanostores'

import type { BrowserCommand } from './types'

interface BrowserActivity { owner: CronBlueprintOwner; kind: BrowserCommand['kind'] }

export const $operationsBrowserActivity = atom<BrowserActivity | null>(null)

export function beginBrowserActivity(owner: CronBlueprintOwner, kind: BrowserCommand['kind']) {
  const activity = { owner, kind }
  $operationsBrowserActivity.set(activity)

  return () => {
    if ($operationsBrowserActivity.get() === activity) { $operationsBrowserActivity.set(null) }
  }
}

export const $showOperationsBrowser = atom(false)
export const $operationsWorkerStatus = atom('等待连接')
