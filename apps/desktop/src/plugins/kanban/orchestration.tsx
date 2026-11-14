/**
 * Orchestration settings — the dashboard's dispatcher-knobs panel, flat-styled:
 * orchestrator profile, default assignee, auto-decompose, and the profile
 * descriptions the decomposer routes by (save / auto-generate per profile).
 */

import {
  Button,
  host,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  useMutation,
  useQuery,
  useQueryClient
} from '@hermes/plugin-sdk'
import { useState } from 'react'

import {
  fetchOrchestration,
  fetchProfiles,
  orchestrationKey,
  profilesKey,
  saveOrchestration,
  saveProfileDescription,
  useKanbanScope
} from './api'
import type { KanbanProfile } from './types'
import { errText, FIELD_LABEL, useKanban } from './ui'

const DEFAULT_SENTINEL = '__default__'

function ProfilePicker({
  label,
  onSave,
  profiles,
  value
}: {
  label: string
  onSave: (name: string) => void
  profiles: KanbanProfile[]
  value: string
}) {
  const k = useKanban()

  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className={FIELD_LABEL}>{label}</span>
      <Select onValueChange={name => onSave(name === DEFAULT_SENTINEL ? '' : name)} value={value || DEFAULT_SENTINEL}>
        <SelectTrigger className="w-44">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={DEFAULT_SENTINEL}>{k.defaultParen}</SelectItem>
          {profiles.map(profile => (
            <SelectItem key={profile.name} value={profile.name}>
              {profile.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  )
}

function ProfileDescriptionRow({ profile }: { profile: KanbanProfile }) {
  const k = useKanban()
  const qc = useQueryClient()
  const scope = useKanbanScope()
  const [draft, setDraft] = useState(profile.description)
  const invalidate = () => void qc.invalidateQueries({ queryKey: profilesKey(scope) })

  const save = useMutation({
    mutationFn: () => saveProfileDescription(profile.name, draft.trim()),
    onError: err => host.notify({ kind: 'error', message: errText(err) }),
    onSuccess: invalidate
  })

  return (
    <div className="flex items-center gap-2">
      <span className="w-24 shrink-0 truncate text-[0.75rem] font-medium text-(--ui-text-secondary)">
        {profile.name}
        {profile.is_default && (
          <span className="ml-1 text-[0.625rem] text-(--ui-text-quaternary)">{k.defaultParen}</span>
        )}
      </span>
      <Input
        className="h-7 flex-1 text-[0.71rem]"
        onChange={event => setDraft(event.target.value)}
        placeholder={k.profileGoodAt}
        value={draft}
      />
      <Button
        disabled={save.isPending || draft.trim() === profile.description}
        onClick={() => save.mutate()}
        size="xs"
        variant="outline"
      >
        {k.save}
      </Button>
    </div>
  )
}

export function OrchestrationPanel() {
  const k = useKanban()
  const qc = useQueryClient()
  const scope = useKanbanScope()
  const { data: settings } = useQuery({ queryKey: orchestrationKey(scope), queryFn: fetchOrchestration })
  const { data: roster } = useQuery({ queryKey: profilesKey(scope), queryFn: fetchProfiles, staleTime: 60_000 })

  const save = useMutation({
    mutationFn: (patch: Record<string, unknown>) => saveOrchestration(patch),
    onError: err => host.notify({ kind: 'error', message: errText(err) }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: orchestrationKey(scope) })
  })

  if (!settings || !roster) {
    return null
  }

  return (
    <div className="flex flex-col gap-4 border-t border-(--ui-stroke-tertiary) px-4 py-3">
      <div className="flex flex-wrap items-end gap-4">
        <ProfilePicker
          label={k.defaultAssignee}
          onSave={name => save.mutate({ default_assignee: name })}
          profiles={roster.profiles}
          value={settings.default_assignee}
        />
        <span className="text-xs text-muted-foreground">自动拆解与自动审核分派未启用</span>
      </div>

      <div className="flex flex-col gap-1.5">
        <span className={FIELD_LABEL}>{k.profileDescriptions}</span>
        <p className="text-[0.6875rem] text-(--ui-text-quaternary)">{k.profileDescriptionsHint}</p>
        {roster.profiles.map(profile => (
          <ProfileDescriptionRow key={`${profile.name}:${profile.description}`} profile={profile} />
        ))}
      </div>
    </div>
  )
}
