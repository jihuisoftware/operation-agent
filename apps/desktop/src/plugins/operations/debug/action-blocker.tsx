import { Button, host } from '@hermes/plugin-sdk'

export function ActionBlocker({ result }: { result: unknown }) {
  if (!result || typeof result !== 'object' || !('blocking_action' in result)) { return null }
  const action = result.blocking_action

  if (!action || typeof action !== 'object' || !('id' in action) || typeof action.id !== 'string') { return null }
  const params = new URLSearchParams({ tab: 'published', record: action.id })
  const scope = action as Record<string, unknown>

  for (const key of ['business_id', 'topic_id'] as const) {
    const value = scope[key]

    if (typeof value === 'string') { params.set(key, value) }
  }

  return <div className="space-y-2 rounded border p-3">
    <p>本次尚未执行。同一内容的原提交仍待核对，新内容可独立发布。</p>
    <Button onClick={() => host.navigate(`/content?${params}`)} variant="outline">查看原发布记录</Button>
  </div>
}
