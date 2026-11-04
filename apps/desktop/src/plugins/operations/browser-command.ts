import type { RefObject } from 'react'

import { executeBrowser } from './browser'
import { BrowserExecution, evidenceDeadline } from './browser-execution'
import { BACKEND_MS } from './browser-timeouts'
import { createBrowserTrace } from './browser-trace'
import type { Api, BrowserCommand, Guest } from './types'

export interface ActiveBrowserExecution { pending: Promise<unknown> | null; context?: BrowserExecution | null }

export async function runBrowserCommand(command: BrowserCommand, guest: Guest, api: Api, worker: string,
  active: RefObject<ActiveBrowserExecution>, sleep: (ms: number) => Promise<unknown>, replace: () => void, isActive: () => boolean) {
  const context = new BrowserExecution(command, guest)
  active.current.context = context
  const trace = createBrowserTrace(command, guest, api, worker, context)

  const pending = context.wait(() => trace.step('execution', () => executeBrowser(command, guest, api, sleep, trace, worker, context)),
    Math.max(1, command.expires * 1000 - Date.now()))

  active.current.pending = pending
  let answer: Record<string, any>

  try {
    try { answer = await pending } catch (error) { answer = context.failure(error) }
    await evidenceDeadline(() => api('/worker/ack', { id: command.id, worker, result: answer }), Date.now() / 1000 + BACKEND_MS / 1000, BACKEND_MS)

    return answer
  } finally {
    context.finish()

    if (active.current.context === context) { active.current.context = null; active.current.pending = null }

    if (context.quarantined && isActive()) { replace() }
  }
}
