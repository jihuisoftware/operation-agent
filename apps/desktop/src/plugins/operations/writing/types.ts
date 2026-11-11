import type { JSONContent } from '@tiptap/core'
export interface Fields {
  title: string
  document: JSONContent
  document_version: number
  source_ids: string[]
  original: boolean
  cover_asset_id: string
}
export interface Draft extends Fields {
  id: string
  revision: number
  updated: string
  archived: boolean
  origin: { kind: string; content_id?: string; content_revision?: string }
  policy_version: number
  last_submission?: { content_id: string }
}
export interface Preview {
  body: string
  asset_ids: string[]
  pending_images: string[]
  issues: string[]
  warnings: string[]
  automatic_cover: boolean
}
export const base = '/content/writing-drafts'

export function fields(draft: Fields): Fields {
  const { title, document, document_version, source_ids, original, cover_asset_id } = draft

  return { title, document, document_version, source_ids, original, cover_asset_id }
}
