import type { Pending } from './journal'
import type { Draft } from './types'

/** Discard a definitively refused candidate before the next ordinary autosave. Keep intervening edits. */
export function rejectedCover(pending: Pending, draft: Draft) {
  if (pending.previous_cover === undefined || draft.cover_asset_id !== pending.fields.cover_asset_id) {
    return {}
  }

  return { draft: { ...draft, cover_asset_id: pending.previous_cover } }
}
