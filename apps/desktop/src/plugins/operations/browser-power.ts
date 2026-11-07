type NativePower = NonNullable<NonNullable<Window['hermesDesktop']>['browserPower']>
type BrowserPowerEntry = Awaited<ReturnType<NativePower['begin']>>
type BrowserPowerOwner = Parameters<NativePower['state']>[0]
type BrowserPowerState = Awaited<ReturnType<NativePower['state']>>

import type { ActiveBrowserExecution } from './browser-command'
import type { Api, BrowserCommand, Guest } from './types'
import { scopePath } from './workspace-state'

interface Owner extends BrowserPowerOwner { business_id?: string; topic_id?: string }
interface Probe { state: string; detail: string }

export function interruption(entry: BrowserPowerEntry) {
  const unknown = entry.phase === 'submission_started'
  const asleep = entry.reason === 'SYSTEM_SUSPENDED'

  return { state: unknown ? 'unknown' : 'blocked', submitted: unknown, dispatch_state: entry.phase,
    error_code: entry.reason || 'BROWSER_UNAVAILABLE', power_epoch: entry.epoch,
    ...(entry.sleep_started_at ? { sleep_started_at: entry.sleep_started_at } : {}),
    ...(entry.resumed_at ? { sleep_resumed_at: entry.resumed_at } : {}),
    error: `${asleep ? '电脑进入睡眠' : '网页执行窗口中断'}，${unknown ? '提交结果未知，请先核对，不能重发' : '网页操作中断，尚未提交；请检查账号后手动继续'}` }
}

/** Replays only interruption facts and asks for a read-only probe; never resumes a batch. */
export function createBrowserPower(owner: Owner, api: Api, active: { current: ActiveBrowserExecution }, status: (message: string) => void, replace: () => void = () => {}) {
  const native = window.hermesDesktop?.browserPower
  let state: BrowserPowerState | undefined
  let checkedEpoch = ''
  let retries = 0
  let nextAttempt = 0
  let retryGeneration = 'initial'
  let disposed = false
  let checking = false
  let paused = false
  let needsReplacement = false
  const admissions = new Map<string, string>()

  const off = native?.onChange(next => {
    if (state && next.epoch === state.epoch && next.suspended === state.suspended) { return }
    state = { ...next, entries: [] }
    checkedEpoch = ''; retries = 0; nextAttempt = 0

    if (next.suspended) {
      needsReplacement = Boolean(active.current.context || active.current.pending)
      active.current.context?.abort('电脑进入睡眠，已停止后续网页操作', 'SYSTEM_SUSPENDED')
      status('电脑进入睡眠，网页任务暂停；唤醒后自动检查账号')
    } else if (needsReplacement) { needsReplacement = false; replace() }
  })

  const recover = async (snapshot: BrowserPowerState) => {
    for (const entry of snapshot.entries.filter(item => item.interrupted)) {
      await api(scopePath('/worker/interrupted', entry), { id: entry.command_id, worker: entry.worker, result: interruption(entry) })
      await native!.acknowledged(owner, entry.command_id)
    }
  }

  const probeAccount = async (snapshot: BrowserPowerState) => {
    const probe = await api<Probe>('/workspaces/worker/revalidate', { account_id: owner.account_id,
      worker: active.current.worker || '', wake_epoch: snapshot.epoch + ':' + retryGeneration,
      request_id: snapshot.epoch + ':' + retryGeneration })

    if (disposed) { return false }
    status(probe.detail)

    if (probe.state === 'ready') { checkedEpoch = snapshot.epoch;

 return true }

    if (probe.state === 'failed') { paused = true }

    return probe.state === 'checking'
  }

  return {
    get epoch() { return state?.epoch },
    async admit(command: BrowserCommand, worker: string, expected: string | undefined) {
      if (!native) { return true }
      const latest = await native.state(owner)

      if (!latest.suspended && latest.epoch === expected) { admissions.set(command.id, latest.epoch);

 return true }

      await api(scopePath('/worker/interrupted', { business_id: command.payload.business_id || owner.business_id!, topic_id: command.payload.topic_id || owner.topic_id! }),
        { id: command.id, worker, result: { state: 'blocked', dispatch_state: 'not_started', submitted: false,
          error_code: 'SYSTEM_SUSPENDED', power_epoch: latest.epoch, error: '领取任务期间电脑进入睡眠，尚未开始网页操作；请手动继续' } })

      return false
    },
    get probeOnly() { return Boolean(native && state?.slept && checkedEpoch !== state.epoch) },
    retry() { retries = 0; nextAttempt = 0; checkedEpoch = ''; retryGeneration = crypto.randomUUID(); paused = false },
    async beforePoll(manual: boolean) {
      if (!native) { return true }

      if (disposed || checking) { return false }

      // Preserve takeover heartbeats; busy=true prevents any command claim.
      if (manual) { return true }

      if (paused || Date.now() < nextAttempt) { return false }
      checking = true

      try {
        const snapshot = await native.state(owner)
        state = snapshot

        if (disposed || snapshot.suspended) { return false }

        if (active.current.pending && snapshot.entries.some(entry => entry.interrupted)) { return false }
        await recover(snapshot)

        if (snapshot.entries.some(entry => entry.interrupted)) { replace();

 return false }

        if (!snapshot.slept || checkedEpoch === snapshot.epoch) { return true }

        return await probeAccount(snapshot)
      } catch (error) {
        retries += 1; nextAttempt = Date.now() + [0, 5000, 15000][Math.min(retries, 2)]

        if (retries >= 3) { paused = true }
        status(`唤醒检查暂未完成：${String(error)}${paused ? '；请点击重试账号检查' : ''}`)

        return false
      } finally { checking = false }
    },
    async begin(command: BrowserCommand, guest: Guest, worker: string) {
      if (!native) { return undefined }

      if (disposed) { throw new Error('执行窗口已切换，任务尚未开始') }
      const snapshot = await native.state(owner)
      state = snapshot
      const scope = command.payload

      return native.begin({ ...owner, business_id: scope.business_id || owner.business_id!, topic_id: scope.topic_id || owner.topic_id!,
        command_id: command.id, worker, expires: command.expires, guest_id: guest.getWebContentsId!() }, admissions.get(command.id) || snapshot.epoch)
    },
    async phase(entry: BrowserPowerEntry, phase: BrowserPowerEntry['phase']) { await native!.phase(entry.command_id, entry.epoch, phase) },
    async interrupted(entry: BrowserPowerEntry) {
      const snapshot = await native!.state(owner)

      return snapshot.entries.find(item => item.command_id === entry.command_id && item.interrupted)
    },
    async abandon(entry: BrowserPowerEntry) { await native!.finish(entry.command_id, entry.epoch, false) },
    async finish(entry: BrowserPowerEntry, wasInterrupted: boolean) {
      if (wasInterrupted) { await native!.acknowledged(owner, entry.command_id) } else { await native!.finish(entry.command_id, entry.epoch) }
    },
    dispose() { disposed = true; off?.() }
  }
}

export type BrowserPower = ReturnType<typeof createBrowserPower>
