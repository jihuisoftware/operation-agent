import { isRecord } from '@hermes/shared/i18n'

import { isMissingRpcMethod } from '@/lib/gateway-rpc'

import { replaceAppLocaleSource } from './registry'

export type BackendLocaleRequest = <T>(method: string, params: Record<string, unknown>) => Promise<T>

/** `i18n.catalog` reply: the pack + overlay layer for one surface, flat. */
export interface BackendLocaleCatalog {
  lang: string
  surface: string
  messages: Record<string, string>
}

export const DESKTOP_SURFACE = 'desktop'

function catalogMessages(value: unknown): Record<string, string> {
  if (!isRecord(value) || !isRecord(value.messages)) {
    return {}
  }

  const messages: Record<string, string> = {}

  for (const [key, text] of Object.entries(value.messages)) {
    if (typeof text === 'string') {
      messages[key] = text
    }
  }

  return messages
}

async function tolerant<T>(call: () => Promise<T>): Promise<T | null> {
  try {
    return await call()
  } catch (error) {
    if (!isMissingRpcMethod(error)) {
      console.debug('[i18n] backend language pack unavailable', error)
    }

    return null
  }
}

/** Refresh the active profile's Chinese overlay; stale responses cannot cross profiles. */
export async function syncBackendLocalePacks(
  request: BackendLocaleRequest,
  isCurrent: () => boolean = () => true
): Promise<void> {
  const catalog = await tolerant(() => request<unknown>('i18n.catalog', { lang: 'zh', surface: DESKTOP_SURFACE }))

  if (!isCurrent() || catalog === null) {
    return
  }

  replaceAppLocaleSource('backend', [{ id: 'zh', translations: catalogMessages(catalog) }])
}
