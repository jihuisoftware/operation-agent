import { BrowserWindow, ipcMain, powerMonitor, webContents, type WebContents } from 'electron'

import { createBrowserPowerJournal } from './browser-power-journal'
import type { BrowserPowerEntry, BrowserPowerOwner } from './browser-power-types'

let journal: ReturnType<typeof createBrowserPowerJournal> | undefined
const owners = new Map<string, number>()
const cleanups = new Map<string, () => void>()

function forget(command: string) { cleanups.get(command)?.(); cleanups.delete(command); owners.delete(command) }

export const browserPowerWorking = () => journal?.working() || false

function trusted(sender: WebContents) {
  if (sender.getType() === 'webview' || !BrowserWindow.fromWebContents(sender)) { throw new Error('仅桌面窗口可管理网页执行') }
}

function owner(value: BrowserPowerOwner) {
  for (const key of ['connectionId', 'profile', 'account_id'] as const) {
    if (key !== 'account_id' && value?.[key] === null) { continue }

    if (typeof value?.[key] !== 'string' || !value[key] || value[key].length > 160) { throw new Error('执行归属无效') }
  }

  return { connectionId: value.connectionId, profile: value.profile, account_id: value.account_id }
}

export function installBrowserPower(file: string, onWork: () => void) {
  if (journal) { return }
  journal = createBrowserPowerJournal(file, id => {
    const guest = webContents.fromId(id)

    if (guest && !guest.isDestroyed() && guest.getType() === 'webview') { guest.close() }
  }, () => {
    onWork()
    const { entries: _entries, ...state } = journal!.state()

    for (const win of BrowserWindow.getAllWindows()) { win.webContents.send('hermes:browser-power', state) }
  })
  ipcMain.handle('hermes:browser-power:state', (event, value) => { trusted(event.sender);

 return journal!.state(owner(value)) })
  ipcMain.handle('hermes:browser-power:begin', (event, value: BrowserPowerEntry, epoch: string) => {
    trusted(event.sender)
    const guest = webContents.fromId(value.guest_id)

    if (!guest || guest.isDestroyed() || guest.getType() !== 'webview' || guest.hostWebContents !== event.sender) { throw new Error('网页实例不属于当前窗口') }

    for (const key of ['command_id', 'worker', 'business_id', 'topic_id'] as const) {
      if (typeof value[key] !== 'string' || !value[key] || value[key].length > 160) { throw new Error('网页命令登记无效') }
    }

    if (!Number.isFinite(value.expires) || value.expires * 1000 > Date.now() + 610_000) { throw new Error('网页命令截止时间无效') }

    const entry = journal!.begin({ ...owner(value), command_id: value.command_id, worker: value.worker,
      business_id: value.business_id, topic_id: value.topic_id, expires: value.expires, guest_id: guest.id }, epoch)

    owners.set(entry.command_id, event.sender.id)
    const destroyed = () => journal!.interruptGuest(guest.id)

    const crashed = () => { journal!.interruptGuest(guest.id);

 if (!guest.isDestroyed()) { guest.close() } }

    guest.once('destroyed', destroyed)
    event.sender.once('render-process-gone', crashed)
    cleanups.set(entry.command_id, () => { guest.off('destroyed', destroyed); event.sender.off('render-process-gone', crashed) })

    return entry
  })
  ipcMain.handle('hermes:browser-power:phase', (event, command: string, epoch: string, phase: BrowserPowerEntry['phase']) => {
    trusted(event.sender)

    if (owners.get(command) !== event.sender.id || !['not_started', 'read_only', 'submission_started'].includes(phase)) { throw new Error('网页命令执行者不匹配') }
    journal!.phase(command, epoch, phase)
  })
  ipcMain.handle('hermes:browser-power:finish', (event, command: string, epoch: string, acknowledged = true) => {
    trusted(event.sender)

    if (owners.get(command) !== event.sender.id) { throw new Error('网页命令执行者不匹配') }
    journal!.finish(command, epoch, acknowledged); forget(command)
  })
  ipcMain.handle('hermes:browser-power:ack', (event, value, command: string) => {
    trusted(event.sender); journal!.acknowledged(owner(value), command); forget(command)
  })
  powerMonitor.on('suspend', () => journal!.suspend())
  powerMonitor.on('resume', () => journal!.resume())
}


export function sendPowerResume(window: BrowserWindow | null) {
  if (window && !window.isDestroyed() && !window.webContents.isDestroyed()) {
    window.webContents.send('hermes:power-resume')
  }
}
