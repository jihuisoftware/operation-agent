import type { Api, BrowserCommand, Guest } from './types'

export interface BrowserTrace {
  step<T>(name: string, operation: () => Promise<T>): Promise<T>
}
export const unrecordedTrace: BrowserTrace = { step: (_name, operation) => operation() }

export function createBrowserTrace(command: BrowserCommand, guest: Guest, api: Api, worker: string): BrowserTrace {
  let sequence = 0

  const send = (body: Record<string, unknown>) => api('/worker/steps', { command_id: command.id, worker, ...body })

  const capture = async () => {
    const evidence: Record<string, unknown> = {}

    try {
      evidence.page = await guest.executeJavaScript(`({ title: document.title, summary: (document.body?.innerText || '').slice(0, 1600) })`)
    } catch (error) { evidence.page_error = String(error) }

    try {
      const image = await guest.capturePage!()
      const data = image.resize({ width: 900 }).toDataURL()

      if (data.length <= 1_500_000) { evidence.screenshot = data } else { evidence.capture_error = '截图超过保存上限' }
    } catch (error) { evidence.capture_error = String(error) }

    return evidence
  }

  return {
    async step<T>(name: string, operation: () => Promise<T>) {
      const number = ++sequence
      const started = new Date().toISOString()
      const tick = performance.now()
      const record = { sequence: number, name, started }
      // A durable start must precede side effects. A failed end write never retries the operation.
      await send({ ...record, phase: 'started', url: guest.getURL() })

      try {
        const result = await operation()
        const problem = result as { state?: string; error?: string; error_code?: string; publication?: { content: string; platform: string } } | null
        const failed = problem?.error || problem?.error_code || ['unknown', 'blocked'].includes(problem?.state || '') || problem?.publication?.content === 'mismatch'
        await send({ ...record, phase: failed ? 'failed' : 'completed', ended: new Date().toISOString(),
          duration_ms: Math.round(performance.now() - tick), url: guest.getURL(), result,
          ...(failed ? { error_code: 'PAGE_RESULT_UNCONFIRMED', ...await capture() } : {}) })

        return result
      } catch (error) {
        await send({ ...record, phase: 'failed', ended: new Date().toISOString(), duration_ms: Math.round(performance.now() - tick),
          url: guest.getURL(), error_code: 'BROWSER_STEP_FAILED', error: String(error), ...await capture() })
        throw error
      }
    }
  }
}
