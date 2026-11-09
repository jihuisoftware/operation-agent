import { host } from '@hermes/plugin-sdk'

import { $workspaces, ownerKey, scopePath } from '../workspace-state'

export function writingPath(query = '') {
  const scope = $workspaces.get()[ownerKey(host.state.requestOwner.get())]?.selected
  const path = `/content/write${query ? '?' + query : ''}`

  return scope ? scopePath(path, scope) : path
}

export function openWriter(fromContent = '') {
  host.navigate(
    writingPath(
      fromContent
        ? `from_content=${encodeURIComponent(fromContent)}&new=${crypto.randomUUID()}`
        : `new=${crypto.randomUUID()}`
    )
  )
}
