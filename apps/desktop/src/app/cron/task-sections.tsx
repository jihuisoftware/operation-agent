import { Navigate, useLocation, useSearchParams } from 'react-router'

import { Button } from '@/components/ui/button'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { ContribBoundary, ContribRender } from '@/contrib/react/boundary'
import { useContributions } from '@/contrib/react/use-contributions'
import { CRON_BLUEPRINTS_AREA, type CronBlueprintContribution } from '@/sdk/cron'

import { ActivityView } from '../activity'
import { UpcomingView } from '../upcoming'

export function useTaskSection() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'history'

  const section =
    (
      { plan: 'blueprints', blueprints: 'blueprints', running: 'running', upcoming: 'upcoming' } as Record<
        string,
        string
      >
    )[tab] || 'jobs'

  const setSection = (value: string) =>
    setParams(previous => {
      const next = new URLSearchParams(previous)
      next.set('tab', ({ blueprints: 'plan', jobs: 'history' } as Record<string, string>)[value] || value)

      if (next.has('historyView')) {
        for (const key of ['historyView', 'day', 'business_id', 'topic_id']) { next.delete(key) }
      }

      return next
    })

  return [section, setSection, section === 'jobs' ? params.get('historyView') : null] as const
}

export function TaskSectionTabs({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <div className="overflow-x-auto px-4 py-2">
      <SegmentedControl
        onChange={onChange}
        options={[
          { id: 'blueprints', label: '运营计划' },
          { id: 'running', label: '正在运行' },
          { id: 'upcoming', label: '待执行' },
          { id: 'jobs', label: '任务与历史' }
        ]}
        value={value}
      />
    </div>
  )
}

export function TaskSectionBody({ section }: { section: string }) {
  return (
    <div className="min-h-0 flex-1 overflow-auto">{section === 'running' ? <ActivityView /> : <UpcomingView />}</div>
  )
}

export function LegacyTaskRoute({ tab }: { tab: string }) {
  const { search } = useLocation()
  const params = new URLSearchParams(search)
  params.set('tab', tab)

  return <Navigate replace to={`/cron?${params}`} />
}


export function FilteredHistory({ id, clear }: { id: string; clear: () => void }) {
  const contributions = useContributions(CRON_BLUEPRINTS_AREA)
  const history = contributions.map(entry => (entry.data as CronBlueprintContribution).history).find(view => view?.id === id)

  return <div className="min-h-0 flex-1 overflow-auto">
    <Button onClick={clear} size="sm" variant="ghost">查看全部任务与历史</Button>
    {history ? <ContribBoundary id={id}><ContribRender render={history.render} /></ContribBoundary>
      : <p role="status">当前筛选视图不可用。</p>}
  </div>
}
