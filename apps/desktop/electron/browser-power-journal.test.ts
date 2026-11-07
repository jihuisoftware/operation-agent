import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { afterEach, expect, it, vi } from 'vitest'

import { createBrowserPowerJournal } from './browser-power-journal'
import { createKeepAwakeController } from './keep-awake-controller'

const directories: string[] = []
afterEach(() => { for (const dir of directories.splice(0)) { fs.rmSync(dir, { recursive: true, force: true }) } })

function fixture() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'browser-power-'))
  directories.push(dir)
  const file = path.join(dir, 'journal.json')
  const destroy = vi.fn()
  const journal = createBrowserPowerJournal(file, destroy, vi.fn())

  const input = { connectionId: 'local', profile: 'work', account_id: 'account', command_id: 'cmd', worker: 'worker',
    business_id: 'business', topic_id: 'topic', guest_id: 55, expires: Date.now() / 1000 + 600 }

  return { journal, file, destroy, input, dir }
}

it('persists submission uncertainty before suspend and rejects a late dispatch after wake', () => {
  const { journal, input, file, destroy } = fixture()
  const entry = journal.begin(input, journal.state().epoch)
  journal.phase(entry.command_id, entry.epoch, 'submission_started')
  journal.suspend(); journal.suspend(); journal.resume(); journal.resume()
  expect(destroy).toHaveBeenCalledTimes(1)
  expect(journal.working()).toBe(false)
  expect(() => journal.phase(entry.command_id, entry.epoch, 'read_only')).toThrow()
  const recovered = createBrowserPowerJournal(file, destroy, vi.fn())
  expect(recovered.state(input).entries[0]).toMatchObject({ phase: 'submission_started', reason: 'SYSTEM_SUSPENDED', interrupted: true })
  expect(recovered.state({ ...input, profile: 'other' }).entries).toEqual([])
  recovered.acknowledged(input, input.command_id)
  expect(recovered.state().entries).toEqual([])
})

it('keeps browser work awake with the existing mode and releases it after completion', () => {
  const { journal, input, dir } = fixture()
  const start = vi.fn(() => 7), stop = vi.fn()

  const controller = createKeepAwakeController({ blocker: { start, stop, isStarted: () => true }, configPath: path.join(dir, 'awake.json'),
    isWorking: journal.working, log: vi.fn(), offer: () => false })

  controller.restore()
  expect(start).not.toHaveBeenCalled()
  const entry = journal.begin(input, journal.state().epoch)
  controller.apply()
  expect(start).toHaveBeenCalledWith('prevent-app-suspension')
  journal.finish(input.command_id, entry.epoch); controller.apply()
  expect(stop).toHaveBeenCalledWith(7)
  controller.setMode('off')
  journal.begin(input, journal.state().epoch); controller.apply()
  expect(start).toHaveBeenCalledTimes(1)
})

it('retains failed acknowledgements and never destroys stale guest ids from a previous process', () => {
  const { journal, input, file, destroy } = fixture()
  const entry = journal.begin(input, journal.state().epoch)
  journal.finish(input.command_id, entry.epoch, false)
  expect(journal.state().entries[0].interrupted).toBe(true)
  destroy.mockClear()
  const recovered = createBrowserPowerJournal(file, destroy, vi.fn())
  recovered.suspend()
  expect(destroy).not.toHaveBeenCalled()
})
