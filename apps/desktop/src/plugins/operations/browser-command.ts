import type { RefObject } from 'react'

import { executeBrowser } from './browser'
import { BrowserExecution, evidenceDeadline } from './browser-execution'
import { type BrowserPower, interruption } from './browser-power'
import { BACKEND_MS } from './browser-timeouts'
import { createBrowserTrace } from './browser-trace'
import type { Api, BrowserCommand, Guest } from './types'

export interface ActiveBrowserExecution { pending: Promise<unknown> | null; worker?: string; context?: BrowserExecution | null }

export async function runBrowserCommand(command: BrowserCommand, guest: Guest, api: Api, worker: string,
  active: RefObject<ActiveBrowserExecution>, sleep: (ms: number) => Promise<unknown>, replace: () => void, isActive: () => boolean, power?: BrowserPower) {
  const context = new BrowserExecution(command, guest)
  active.current.context = context
  const trace = createBrowserTrace(command, guest, api, worker, context)

  let entry: Awaited<ReturnType<BrowserPower['begin']>>
  let acknowledged = false

  const pending = context.wait(async () => {
    entry = await power?.begin(command, guest, worker)
    context.assert()

    if (entry) {
      context.beforeSubmission = () => power!.phase(entry!, 'submission_started')
      await power!.phase(entry, 'read_only')
    }

    context.assert()

    return trace.step('execution', () => executeBrowser(command, guest, api, sleep, trace, worker, context))
  }, Math.max(1, command.expires * 1000 - Date.now()))

  active.current.pending = pending
  let answer: Record<string, any>

  try {
    try { answer = await pending } catch (error) { answer = context.failure(error) }
    const stopped = entry && await power!.interrupted(entry)

    if (stopped) { answer = interruption(stopped) }
    await evidenceDeadline(() => api(stopped ? '/worker/interrupted' : '/worker/ack', { id: command.id, worker, result: answer }), Date.now() / 1000 + BACKEND_MS / 1000, BACKEND_MS)

    if (entry) { await power!.finish(entry, Boolean(stopped)) }
    acknowledged = true

    return answer
  } finally {
    try {
      if (entry && !acknowledged) { await power!.abandon(entry) }
    } finally {
      context.finish()

      if (active.current.context === context) { active.current.context = null; active.current.pending = null }

      if (context.quarantined && isActive()) { replace() }
    }
  }
}
