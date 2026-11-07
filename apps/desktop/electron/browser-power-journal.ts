import { randomUUID } from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'

import type { BrowserPowerEntry, BrowserPowerOwner, BrowserPowerState } from './browser-power-types'

export function samePowerOwner(a: BrowserPowerOwner, b: BrowserPowerOwner) {
  return a.connectionId === b.connectionId && a.profile === b.profile && a.account_id === b.account_id
}

/** Written before dispatch; unfinished entries survive a renderer or application restart. */
export function createBrowserPowerJournal(file: string, destroy: (id: number) => void, changed: () => void) {
  let epoch = randomUUID()
  let suspended = false
  let slept = false
  let entries: BrowserPowerEntry[] = []

  if (fs.existsSync(file)) {
    const saved = JSON.parse(fs.readFileSync(file, 'utf8')) as BrowserPowerEntry[]
    entries = saved.map(entry => ({ ...entry, interrupted: true, reason: entry.reason || 'BROWSER_UNAVAILABLE' }))
    slept = entries.length > 0
  }

  const persist = () => {
    fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 })
    fs.writeFileSync(file + '.tmp', JSON.stringify(entries), { mode: 0o600 })
    fs.renameSync(file + '.tmp', file)
  }

  const state = (owner?: BrowserPowerOwner): BrowserPowerState => ({ epoch, suspended, slept,
    entries: entries.filter(entry => !owner || samePowerOwner(entry, owner)).map(entry => ({ ...entry })) })

  const find = (command: string, expected: string) => {
    const entry = entries.find(item => item.command_id === command && item.epoch === expected)

    if (!entry) { throw new Error('网页命令登记不存在') }

    return entry
  }

  return {
    state,
    working: () => entries.some(entry => !entry.interrupted && entry.expires * 1000 > Date.now()),
    begin(input: Omit<BrowserPowerEntry, 'epoch' | 'phase'>, expected: string) {
      if (suspended || expected !== epoch || input.expires * 1000 <= Date.now()) { throw new Error('电源代次已变化，禁止旧任务派发') }

      if (entries.some(entry => entry.command_id === input.command_id)) { throw new Error('网页命令已登记') }
      const entry: BrowserPowerEntry = { ...input, epoch, phase: 'not_started' }
      entries.push(entry); persist(); changed()

      return { ...entry }
    },
    phase(command: string, expected: string, phase: BrowserPowerEntry['phase']) {
      const entry = find(command, expected)

      if (suspended || expected !== epoch || entry.interrupted || entry.expires * 1000 <= Date.now()) { throw new Error('旧网页任务已停止') }

      if (entry.phase !== 'submission_started') { entry.phase = phase }
      persist()
    },
    finish(command: string, expected: string, acknowledged = true) {
      const entry = find(command, expected)

      if (!acknowledged) { entry.interrupted = true; entry.reason ||= 'BROWSER_UNAVAILABLE'; persist(); changed(); destroy(entry.guest_id) }

      // An interrupted entry is retained until the backend accepts the interruption receipt.
      if (!entry.interrupted) { entries = entries.filter(item => item !== entry); persist(); changed() }
    },
    acknowledged(owner: BrowserPowerOwner, command: string) {
      entries = entries.filter(entry => entry.command_id !== command || !samePowerOwner(owner, entry))
      persist(); changed()
    },
    interruptGuest(id: number) {
      for (const entry of entries.filter(item => item.guest_id === id && !item.interrupted)) {
        entry.interrupted = true; entry.reason = 'BROWSER_UNAVAILABLE'
      }

      persist(); changed()
    },
    suspend() {
      if (suspended) { return }
      suspended = true; slept = true; epoch = randomUUID()
      const active = entries.filter(item => !item.interrupted)

      for (const entry of active) {
        entry.interrupted = true; entry.reason = 'SYSTEM_SUSPENDED'; entry.sleep_started_at = Date.now() / 1000
      }

      persist(); changed()

      for (const id of new Set(active.map(entry => entry.guest_id))) { destroy(id) }
    },
    resume() {
      if (!suspended) { return }
      suspended = false

      for (const entry of entries.filter(item => item.reason === 'SYSTEM_SUSPENDED' && !item.resumed_at)) { entry.resumed_at = Date.now() / 1000 }
      persist(); changed()
    }
  }
}
