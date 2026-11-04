/** Poll read-only evidence; submission callbacks must never be passed here. */
export async function waitForRead<T>(read: () => Promise<T>, ready: (value: T) => boolean, timeoutMs = 15000, allowUnknown = false, sleep: (ms: number) => Promise<unknown> = ms => new Promise(resolve => setTimeout(resolve, ms))): Promise<T> {
  const deadline = Date.now() + timeoutMs

  for (;;) {
    const value = await read()

    if (ready(value)) { return value }

    if (Date.now() >= deadline) {
      if (allowUnknown) { return value }
      throw new BrowserReadinessError('等待网页就绪超时，未执行后续提交')
    }

    await sleep(500)
  }
}

export class BrowserReadinessError extends Error {
  constructor(message: string, readonly code = 'PAGE_NOT_READY') { super(message) }
}
