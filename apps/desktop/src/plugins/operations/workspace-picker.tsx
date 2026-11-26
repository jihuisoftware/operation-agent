import { Button, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useEffect } from 'react'

import { guardWorkspaceChange, WORKSPACES_PATH } from './workspace-navigation'
import { $workspaces, chooseScope, loadWorkspaces, ownerKey } from './workspace-state'

export function WorkspacePicker({ ctx }: { ctx: PluginContext }) {
  const owner = useValue(host.state.requestOwner)
  const state = useValue($workspaces)[ownerKey(owner)]
  useEffect(() => {
    void loadWorkspaces(ctx, owner)
  }, [ctx, owner])
  const { catalog, selected } = state || {}
  if (!catalog || !selected) return <p className="p-2 text-xs">{state?.error || '读取业务空间…'}</p>

  return (
    <section aria-label="业务与主题" className="space-y-1 p-2 text-xs">
      <Button
        onClick={() => {
        }}
        size="sm"
        variant="link"
      >
        业务与主题
      </Button>
      <select
        aria-label="当前业务与主题"
        className="w-full rounded border bg-background p-2"
        value={selected.topic_id}
        onChange={event => {
          const topic = catalog.topics.find(t => t.id === event.target.value)
          if (topic)
            guardWorkspaceChange(owner, () =>
              chooseScope(owner, { business_id: topic.business_id, topic_id: topic.id })
            )
        }}
      >
        {catalog.businesses.map(b => (
          <optgroup key={b.id} label={b.name}>
            {catalog.topics
              .filter(t => t.business_id === b.id && (t.id === selected.topic_id || (!t.archived && !b.archived)))
              .map(t => (
                <option key={t.id} value={t.id}>
                  {b.name} / {t.name}
                  {t.archived || b.archived ? '（已归档）' : ''}
                </option>
              ))}
          </optgroup>
        ))}
      </select>
      
    </section>
  )
}
