import type { RecordRow } from './types'

export function versionRequest(row: RecordRow, changes: Record<string, unknown>, cancelSchedule = false) {
  if (typeof row.content_revision !== 'string' || typeof row.policy_version !== 'number') { throw new Error('请重新打开稿件，读取最新版本后再保存') }
  const release = row.release as { revision?: number } | undefined

  return { ...changes, request_id: crypto.randomUUID(), content_revision: row.content_revision, version: row.policy_version,
    cancel_original_schedule: cancelSchedule, ...(cancelSchedule ? { expected_release_revision: release?.revision } : {}) }
}

export function localInput(value: string) {
  const date = new Date(value)
  const pad = (number: number) => String(number).padStart(2, '0')

  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}
