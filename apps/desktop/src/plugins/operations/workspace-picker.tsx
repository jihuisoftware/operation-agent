import { Button, Codicon, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator,
  DropdownMenuTrigger, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useEffect } from 'react'

import { useSidebarLoginStatus } from './login-activity'
import { guardWorkspaceChange, WORKSPACES_PATH } from './workspace-navigation'
import { $workspaces, chooseScope, loadWorkspaces, ownerKey } from './workspace-state'

export function WorkspacePicker({ ctx }: { ctx: PluginContext }) {
  const owner = useValue(host.state.requestOwner)
  useSidebarLoginStatus(ctx, owner)
  const state = useValue($workspaces)[ownerKey(owner)]
  useEffect(() => {
    void loadWorkspaces(ctx, owner)
  }, [ctx, owner])

  const { catalog, selected } = state || {}
  const choices = catalog?.businesses.flatMap(business => catalog.topics
    .filter(topic => topic.business_id === business.id && (topic.id === selected?.topic_id || (!topic.archived && !business.archived)))
    .map(topic => ({ topic, label: business.name + ' / ' + topic.name + (business.archived || topic.archived ? '（已归档）' : '') }))) ?? []
  const current = choices.find(choice => choice.topic.id === selected?.topic_id)
  const title = current?.label ?? state?.error ?? (catalog ? '选择业务与主题' : '读取业务空间…')

  return <DropdownMenu>
    <DropdownMenuTrigger asChild>
      <Button aria-label={'当前业务与主题，' + title} className="mb-1 w-full justify-between [-webkit-app-region:no-drag]" size="sm" title={title} variant="ghost">
        <span className="truncate">{title}</span><Codicon className="size-3 shrink-0" name="chevron-down" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" aria-label="业务与主题">
      {choices.map(({ topic, label }) => <DropdownMenuItem aria-current={topic.id === selected?.topic_id || undefined}
        key={topic.id} onSelect={() => {
          if (topic.id !== selected?.topic_id) guardWorkspaceChange(owner, () => chooseScope(owner, { business_id: topic.business_id, topic_id: topic.id }))
        }}>
        <span className="min-w-0 truncate" title={label}>{label}</span>
        {topic.id === selected?.topic_id && <Codicon className="ml-auto size-3 shrink-0" name="check" />}
      </DropdownMenuItem>)}
      {choices.length > 0 && <DropdownMenuSeparator />}
      <DropdownMenuItem onSelect={() => guardWorkspaceChange(owner, () => host.navigate(WORKSPACES_PATH))}>管理业务与主题</DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
}
