import { type BrowserExecution, BrowserExecutionError } from './browser-execution'
import { LOGIN_MS } from './browser-timeouts'
import type { LoginObservation } from './login-state'

const STABLE_NEGATIVE_MS = 3000
const negative = (observation: LoginObservation) => ['logged_out', 'verification'].includes(observation.state)

/** One page must expose the same negative evidence over time; past login is never an override. */
export class LoginEvidence {
  private candidate: { scope: string; state: string; since: number } | null = null

  observe(observation: LoginObservation, scope: string): LoginObservation | null {
    if (observation.loading || !negative(observation)) {
      this.candidate = null

      return observation.loading ? null : observation
    }

    if (!this.candidate || this.candidate.scope !== scope || this.candidate.state !== observation.state) {
      this.candidate = { scope, state: observation.state, since: Date.now() }
    }

    return Date.now() - this.candidate.since >= STABLE_NEGATIVE_MS ? observation : null
  }

  reset() { this.candidate = null }
}

export async function confirmLogin(read: () => Promise<LoginObservation>, scope: () => string,
  execution: BrowserExecution, requireIdentity: boolean, sleep: (ms: number) => Promise<unknown> = ms => new Promise(resolve => setTimeout(resolve, ms))) {
  const evidence = new LoginEvidence()
  const deadline = execution.workNow() + LOGIN_MS
  let waitingForIdentity = requireIdentity

  while (execution.workNow() < deadline) {
    execution.assert()
    const page = scope()
    const loadingVersion = execution.loadingVersion
    const observation = await execution.wait(read, execution.remainingMs(), false, '账号观察复合步骤')

    if (loadingVersion !== execution.loadingVersion) { evidence.reset(); waitingForIdentity = true }

    if (page !== scope()) { evidence.reset(); waitingForIdentity = true;

 continue }

    if (negative(observation)) { waitingForIdentity = true }
    const confirmed = evidence.observe(observation, page)

    if (confirmed && confirmed.state !== 'unknown' && (confirmed.state !== 'logged_in' || !requireIdentity || confirmed.account_id)) { return confirmed }

    if (confirmed?.state === 'unknown' && !waitingForIdentity) { return confirmed }
    await execution.wait(() => sleep(Math.max(0, Math.min(500, deadline - execution.workNow()))), 5000, false, '账号观察时钟')
  }

  throw new BrowserExecutionError('登录状态仍未确认，请等待页面加载完成后手动继续', 'BROWSER_UNAVAILABLE')
}
