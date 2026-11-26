import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, expect, it } from 'vitest'

import { registry } from '@/contrib/registry'
import { CRON_BLUEPRINTS_AREA, type CronBlueprintContribution } from '@/sdk/cron'

import { ContributedBlueprints } from './contributed-blueprints'

afterEach(cleanup)

it('keeps an editor mounted during parent refreshes and re-homes it on Profile change', () => {
  function Editor({ profile }: { profile: string | null }) {
    const [text, setText] = useState(profile || '')

    return <input aria-label="草稿" onChange={e => setText(e.target.value)} value={text} />
  }

  const dispose = registry.register({
    id: 'test:blueprints',
    area: CRON_BLUEPRINTS_AREA,
    data: { render: ({ owner }) => <Editor profile={owner.profile} /> } satisfies CronBlueprintContribution
  })

  try {
    const { rerender } = render(<ContributedBlueprints profile="one" view="blueprints" />)
    fireEvent.change(screen.getByLabelText('草稿'), { target: { value: '未保存' } })
    rerender(<ContributedBlueprints profile="one" view="blueprints" />)
    expect((screen.getByLabelText('草稿') as HTMLInputElement).value).toBe('未保存')
    rerender(<ContributedBlueprints profile="two" view="blueprints" />)
    expect((screen.getByLabelText('草稿') as HTMLInputElement).value).toBe('two')
  } finally {
    dispose()
  }
})

it('renders the requested history contribution and returns to the ordinary jobs tab', async () => {
  const { MemoryRouter, useLocation } = await import('react-router')
  const { FilteredHistory, useTaskSection } = await import('./task-sections')
  function History() {
    const [, setTab, id] = useTaskSection()
    const location = useLocation()
    return id ? <FilteredHistory clear={() => setTab('jobs')} id={id} /> : <p>{location.search}</p>
  }
  const dispose = registry.register({ id: 'test:history', area: CRON_BLUEPRINTS_AREA,
    data: { render: () => null, history: { id: 'operations.failed', render: () => <p>所选主题失败记录</p> } } satisfies CronBlueprintContribution })
  try {
    render(<MemoryRouter initialEntries={['/cron?tab=history&historyView=operations.failed&day=2026-11-26&business_id=b&topic_id=t']}>
      <History />
    </MemoryRouter>)
    expect(screen.getByText('所选主题失败记录')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '查看全部任务与历史' }))
    expect(screen.getByText('?tab=history')).toBeTruthy()
  } finally { dispose() }
})

it.each(['plan', 'blueprints'])('replaces legacy %s links with a scoped plan without adding a history entry', async tab => {
  const { MemoryRouter, Routes, Route, useLocation, useNavigate } = await import('react-router')
  const { LegacyPlan } = await import('./task-sections')
  function Destination() {
    const location = useLocation()
    const navigate = useNavigate()
    return <button onClick={() => navigate(-1)}>{location.pathname + location.search}</button>
  }
  const dispose = registry.register({ id: 'test:plan', area: CRON_BLUEPRINTS_AREA, data: { planPath: '/operations/workspaces?view=plan' } })
  try {
    render(<MemoryRouter initialEntries={['/origin', '/cron?tab=' + tab + '&business_id=b&topic_id=t']}>
      <Routes><Route path="/cron" element={<LegacyPlan fallback={null} />} /><Route path="*" element={<Destination />} /></Routes>
    </MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: '/operations/workspaces?view=plan&business_id=b&topic_id=t' }))
    expect(await screen.findByRole('button', { name: '/origin' })).toBeTruthy()
  } finally { dispose() }
})
