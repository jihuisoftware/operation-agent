import { randomUUID } from 'node:crypto'
import fs from 'node:fs'

import type { BrowserPowerEntry } from './browser-power-types'

function validEntry(value: unknown): value is BrowserPowerEntry {
  if (!value || typeof value !== 'object') { return false }
  const row = value as Record<string, unknown>
  const strings = ['account_id', 'command_id', 'worker', 'business_id', 'topic_id', 'epoch']
  const owners = ['connectionId', 'profile']

  return strings.every(key => typeof row[key] === 'string' && Boolean(row[key])) &&
    owners.every(key => row[key] === null || typeof row[key] === 'string') &&
    typeof row.expires === 'number' && Number.isFinite(row.expires) &&
    Number.isInteger(row.guest_id) && ['not_started', 'read_only', 'submission_started'].includes(String(row.phase))
}

/** Preserve damaged evidence; never turn an unreadable journal into permission to submit. */
export function readBrowserPowerJournal(file: string): { entries: BrowserPowerEntry[]; slept: boolean; error?: string } {
  let raw: string

  try { raw = fs.readFileSync(file, 'utf8') } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') { return { entries: [], slept: false } }
    console.warn('[browser-power] 无法读取网页恢复记录', error)

    return { entries: [], slept: true, error: '网页恢复记录无法读取；请检查应用数据目录权限后重启，网页任务暂不派发' }
  }

  let saved: unknown

  try { saved = JSON.parse(raw) } catch { saved = null }
  const entries = Array.isArray(saved) ? saved.filter(validEntry) : []
  const damaged = !Array.isArray(saved) || entries.length !== saved.length

  if (damaged) {
    try {
      const backup = `${file}.invalid-${randomUUID()}`
      fs.copyFileSync(file, backup, fs.constants.COPYFILE_EXCL)
      // Persist surviving entries before exposing a working journal. A second
      // restart must not lose an uncertain submission from a mixed record set.
      fs.writeFileSync(file + '.tmp', JSON.stringify(entries), { mode: 0o600 })
      fs.renameSync(file + '.tmp', file)
      console.warn('[browser-power] 网页恢复记录损坏，已保留原文件：', backup)
    } catch (error) {
      console.warn('[browser-power] 无法隔离损坏的网页恢复记录', error)

      return { entries, slept: true, error: '网页恢复记录无法修复；请检查应用数据目录后重启，网页任务暂不派发' }
    }
  }

  return { entries, slept: damaged || entries.length > 0 }
}
