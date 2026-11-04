import { type BrowserExecution, evidenceDeadline } from './browser-execution'

/** Poll read-only evidence; submission callbacks must never be passed here. */
export async function waitForRead<T>(read: () => Promise<T>, ready: (value: T) => boolean, timeoutMs = 15000, allowUnknown = false, sleep: (ms: number) => Promise<unknown> = ms => new Promise(resolve => setTimeout(resolve, ms)), execution?: BrowserExecution): Promise<T> {
  const now = () => execution ? execution.workNow() : Date.now()
  const deadline = now() + timeoutMs
  let previous: { value: T } | undefined

  for (;;) {
    execution?.assert()

    if (previous && now() >= deadline) {
      if (allowUnknown) { return previous.value }
      throw new BrowserReadinessError('等待网页就绪超时，未执行后续提交')
    }

    // The callback composes independently bounded backend/load/script work. A second
    // short timer here would charge network loading against the script's budget again.
    const value = execution ? await execution.wait(read, execution.remainingMs(), false, '只读复合步骤') :
      await evidenceDeadline(read, Date.now() / 1000 + Math.max(timeoutMs, 10000) / 1000, Math.max(timeoutMs, 10000))

    previous = { value }

    if (ready(value)) { return value }

    if (now() >= deadline) {
      if (allowUnknown) { return value }
      throw new BrowserReadinessError('等待网页就绪超时，未执行后续提交')
    }

    if (execution) { await execution.wait(() => sleep(500), 5000, false, '轮询时钟') } else { await sleep(500) }
  }
}

export class BrowserReadinessError extends Error {
  constructor(message: string, readonly code = 'PAGE_NOT_READY') { super(message) }
}
