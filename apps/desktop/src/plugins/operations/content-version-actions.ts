import type { JSONContent } from '@tiptap/core'

import type { RecordRow } from './types'
import { projection } from './writing/projection'

export function versionRequest(row: RecordRow, changes: Record<string, unknown>) {
  if (typeof row.content_revision !== 'string' || typeof row.policy_version !== 'number') { throw new Error('请重新打开稿件，读取最新版本后再保存') }
  const release = row.release as { revision?: number } | undefined

  return { ...changes, request_id: crypto.randomUUID(), content_revision: row.content_revision, version: row.policy_version,
    ...(typeof release?.revision === 'number' ? { expected_release_revision: release.revision } : {}) }
}

export function localInput(value: string) {
  const date = new Date(value)
  const pad = (number: number) => String(number).padStart(2, '0')

  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function coverAssetIds(row: RecordRow, cover: string) {
  const images = row.editor_document ? projection(row.editor_document as JSONContent).asset_ids : ((row.asset_ids || []) as string[]).slice(1)

  return [...new Set([cover, ...images])]
}
