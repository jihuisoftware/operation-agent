import { useStore } from '@nanostores/react'
import { useCallback, useMemo } from 'react'

import { $apiRequestScope } from '@/api/client'
import { Button } from '@/components/ui/button'
import { ContribBoundary, ContribRender } from '@/contrib/react/boundary'
import { useContributions } from '@/contrib/react/use-contributions'
import { CRON_BLUEPRINTS_AREA, type CronBlueprintContribution } from '@/sdk/cron'

export function ContributedBlueprints({
  profile,
  view
}: {
  profile: string
  view: 'blueprints' | 'summary' | 'upcoming'
}) {
  const scope = useStore($apiRequestScope)
  const owner = useMemo(() => ({ connectionId: scope.connectionId, profile }), [scope.connectionId, profile])
  const contributions = useContributions(CRON_BLUEPRINTS_AREA)

  if (!contributions.length) {
    return view === 'summary' ? null : (
      <div className="space-y-3 p-6 text-sm">
        <p>运营蓝图插件尚未启用或加载失败。</p>
        <p className="text-muted-foreground">请在功能与插件中启用运营插件；更新后重启 Desktop 和 Server。</p>
        <Button
          onClick={() => {
            window.location.hash = '/settings?tab=plugins'
          }}
          variant="outline"
        >
          管理插件
        </Button>
      </div>
    )
  }

  return (
    <>
      {contributions.map(entry => (
        <ContributionEntry
          data={entry.data as CronBlueprintContribution}
          id={entry.id}
          key={`${entry.id}:${JSON.stringify(owner)}:${view}`}
          owner={owner}
          view={view}
        />
      ))}
    </>
  )
}

function ContributionEntry({
  id,
  data,
  owner,
  view
}: {
  id: string
  data: CronBlueprintContribution
  owner: { connectionId: string | null; profile: string }
  view: 'blueprints' | 'summary' | 'upcoming'
}) {
  const render = useCallback(
    () => (view === 'upcoming' ? data.renderUpcoming?.({ owner }) : data.render({ owner, view })),
    [data, owner, view]
  )

  return (
    <ContribBoundary id={id}>
      <ContribRender render={render} />
    </ContribBoundary>
  )
}
