import type { WebhookCreatePayload, WebhookCreateResponse, WebhookEnableResponse, WebhooksResponse } from '@/types/hermes'

import { hermesApi, profileScoped } from './client'

// -- Webhooks (subscription CRUD) --------------------------------------------
// The webhook receiver is its own gateway platform; subscriptions live in a
// shared JSON store the CLI/dashboard also drive. Enable mutates config and
// best-effort restarts the gateway; subscription changes hot-reload.

/** `profile` = the backend owner this view captured at mount; omitted → the
 *  ambient request scope. Keyed explicitly so a view that survives an active
 *  profile switch keeps talking to the profile it belongs to (#71352). */
export function getWebhooks(profile?: null | string): Promise<WebhooksResponse> {
  return hermesApi<WebhooksResponse>({
    ...profileScoped(profile),
    path: '/api/webhooks'
  })
}

export function enableWebhooks(profile?: null | string): Promise<WebhookEnableResponse> {
  return hermesApi<WebhookEnableResponse>({
    ...profileScoped(profile),
    path: '/api/webhooks/enable',
    method: 'POST'
  })
}

export function createWebhook(body: WebhookCreatePayload, profile?: null | string): Promise<WebhookCreateResponse> {
  return hermesApi<WebhookCreateResponse>({
    ...profileScoped(profile),
    path: '/api/webhooks',
    method: 'POST',
    body
  })
}

export function deleteWebhook(name: string, profile?: null | string): Promise<{ ok: boolean }> {
  return hermesApi<{ ok: boolean }>({
    ...profileScoped(profile),
    path: `/api/webhooks/${encodeURIComponent(name)}`,
    method: 'DELETE'
  })
}

export function setWebhookEnabled(
  name: string,
  enabled: boolean,
  profile?: null | string
): Promise<{ enabled: boolean; name: string; ok: boolean }> {
  return hermesApi<{ enabled: boolean; name: string; ok: boolean }>({
    ...profileScoped(profile),
    path: `/api/webhooks/${encodeURIComponent(name)}/enabled`,
    method: 'PUT',
    body: { enabled }
  })
}
