import { WaitDiagnostics } from './browser-wait-diagnostics'
import type { BrowserCommand, Guest } from './types'

export interface ExecutionBlock { error_code: string; error: string; cause_at?: number }
export type DispatchState = 'not_started' | 'read_only' | 'submission_started'

export class BrowserExecutionError extends Error {
  constructor(message: string, readonly code: string) { super(message) }
}

const owners = new WeakMap<Guest, BrowserExecution>()
let nextEpoch = 0

/** Cancellation fences every continuation; an unresponsive guest is detached before it can be reused. */
export class BrowserExecution {
  readonly controller = new AbortController()
  readonly epoch = ++nextEpoch
  dispatchState: DispatchState = 'not_started'
  quarantined = false
  private pendingGuest = 0
  private ended = false
  private inheritedBlock: ExecutionBlock | null = null
  private waits = new WaitDiagnostics()
  private timeoutEvidence?: ReturnType<WaitDiagnostics['timeout']>
  private pageEvidence?: { origin: string; path: string; main_frame_loading?: boolean }
  private loadingStarted?: number
  private loadingDepth = 0
  private loadingElapsed = 0
  loadingVersion = 0

  remainingMs() { return Math.max(1, this.command.expires * 1000 - Date.now()) }

  workNow() { return Date.now() - this.loadingElapsed - (this.loadingStarted === undefined ? 0 : Date.now() - this.loadingStarted) }

  async loading<T>(operation: () => Promise<T>, timeoutMs: number, label: string): Promise<T> {
    if (this.loadingDepth++ === 0) { this.loadingStarted = Date.now(); this.loadingVersion += 1 }

    try { return await this.wait(operation, timeoutMs, true, label) } finally {
      if (--this.loadingDepth === 0) {
        this.loadingElapsed += Date.now() - this.loadingStarted!
        this.loadingStarted = undefined
      }
    }
  }

  page(url: URL) {
    this.pageEvidence = { origin: url.origin, path: url.pathname, main_frame_loading: this.guest.isLoadingMainFrame?.() }
  }

  constructor(readonly command: BrowserCommand, readonly guest: Guest) {
    owners.get(guest)?.abort('网页执行已由新任务接管', 'BROWSER_UNAVAILABLE')
    owners.set(guest, this)
  }

  assert() {
    if (this.controller.signal.aborted) { throw this.controller.signal.reason }

    if (this.ended || owners.get(this.guest) !== this) { throw new BrowserExecutionError('旧网页任务已停止', 'BROWSER_UNAVAILABLE') }

    if (Date.now() >= this.command.expires * 1000) {
      this.abort('网页任务已到期，已停止后续操作', 'COMMAND_EXPIRED')
      throw this.controller.signal.reason
    }
  }

  abort(message: string, code: string) {
    if (this.controller.signal.aborted || this.ended) { return }
    this.controller.abort(new BrowserExecutionError(message, code))

    if (this.pendingGuest > 0) {
      this.quarantined = true
      this.guest.remove?.()
    }
  }

  observe(state: string, account: string) {
    if (state === 'logged_out') { this.abort('平台登录已失效，请重新登录后手动继续', 'AUTH_REQUIRED') }

    if (state === 'verification') { this.abort('平台要求安全验证，请完成验证后手动继续', 'VERIFICATION_REQUIRED') }

    if (state === 'logged_in' && this.command.payload.account_id && this.command.payload.account_id !== account) {
      this.abort('当前登录账号不匹配，已停止执行', 'ACCOUNT_CHANGED')
    }
  }

  block(value: ExecutionBlock | null | undefined) {
    if (value && !['account', 'verify'].includes(this.command.kind) && !this.controller.signal.aborted && !this.ended) {
      this.inheritedBlock = value
      this.abort(value.error, value.error_code)
    }
  }

  async wait<T>(operation: () => Promise<T>, timeoutMs = 5000, guestOperation = false, label = '网页操作'): Promise<T> {
    this.assert()
    const remaining = this.command.expires * 1000 - Date.now()
    const waitId = this.waits.start(label, Math.min(remaining, timeoutMs), guestOperation)
    let timer: ReturnType<typeof setTimeout> | undefined
    let aborted: (() => void) | undefined

    const pending = Promise.resolve().then(async () => {
      this.assert()

      if (guestOperation) { this.pendingGuest += 1; this.dispatchState = this.dispatchState === 'not_started' ? 'read_only' : this.dispatchState }

      try { return await operation() } finally { if (guestOperation) { this.pendingGuest -= 1 } }
    })

    try {
      const result = await Promise.race([pending, new Promise<never>((_, reject) => {
        aborted = () => reject(this.controller.signal.reason)
        this.controller.signal.addEventListener('abort', aborted, { once: true })
        timer = setTimeout(() => {
          this.timeoutEvidence = this.waits.timeout(waitId)
          this.abort(remaining <= timeoutMs ? '网页任务已到期，已停止后续操作' : `${label}超时，已停止本次执行，请重新打开网页后手动继续`,
            remaining <= timeoutMs ? 'COMMAND_EXPIRED' : 'BROWSER_UNAVAILABLE')
        }, Math.min(remaining, timeoutMs))
      })])

      this.assert()

      return result
    } finally {
      clearTimeout(timer)
      this.waits.finish(waitId)

      if (aborted) { this.controller.signal.removeEventListener('abort', aborted) }
    }
  }

  submission() { this.assert(); this.dispatchState = 'submission_started' }

  failure(error: unknown) {
    const cause = this.inheritedBlock?.cause_at

    return { state: this.dispatchState === 'submission_started' ? 'unknown' : 'blocked',
      error: error instanceof Error ? error.message : String(error),
      error_code: error instanceof BrowserExecutionError ? error.code : 'BROWSER_UNAVAILABLE',
      dispatch_state: this.dispatchState, submitted: this.dispatchState === 'submission_started',
      ...(this.timeoutEvidence ? { wait_diagnostics: { ...this.timeoutEvidence, page: this.pageEvidence } } : {}),
      ...(typeof cause === 'number' && Number.isFinite(cause) ? { cause_at: cause } : {}) }
  }

  finish() {
    this.ended = true

    if (owners.get(this.guest) === this) { owners.delete(this.guest) }
  }
}

/** Evidence is best effort and never extends an expired command or blocks its terminal receipt. */
export async function evidenceDeadline<T>(operation: () => Promise<T>, expires: number, timeoutMs = 3000): Promise<T> {
  const remaining = Number.isFinite(expires) ? expires * 1000 - Date.now() : timeoutMs

  if (remaining <= 0) { throw new BrowserExecutionError('任务已到期，停止取证', 'COMMAND_EXPIRED') }
  let timer: ReturnType<typeof setTimeout> | undefined

  try {
    return await Promise.race([Promise.resolve().then(operation), new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new BrowserExecutionError('网页取证超时', 'BROWSER_UNAVAILABLE')), Math.min(timeoutMs, remaining))
    })])
  } finally { clearTimeout(timer) }
}
