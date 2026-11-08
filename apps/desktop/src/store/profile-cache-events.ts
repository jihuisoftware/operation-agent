/** Renderer recovery stores follow the same Profile lifecycle as session tiles. */
export interface ProfileCacheChange {
  connectionId: string
  profile: string
  renamedTo?: string
}
const listeners = new Set<(change: ProfileCacheChange) => void>()

export function onProfileCacheChange(listener: (change: ProfileCacheChange) => void) {
  listeners.add(listener)

  return () => {
    listeners.delete(listener)
  }
}

export function notifyProfileCacheChange(change: ProfileCacheChange) {
  for (const listener of listeners) {
    listener(change)
  }
}
