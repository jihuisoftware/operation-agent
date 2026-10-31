import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { atom } from 'nanostores'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AutomationBlueprint, CronJob } from '@/hermes'

const hermes = vi.hoisted(() => ({
  getAutomationBlueprints: vi.fn(),
  getCronJobs: vi.fn(),
  instantiateAutomationBlueprint: vi.fn()
}))

vi.mock('@/hermes', async importOriginal => ({
  ...(await importOriginal<Record<string, unknown>>()),
  getAutomationBlueprints: hermes.getAutomationBlueprints,
  getCronDeliveryTargets: vi.fn(async () => []),
  getCronJobs: hermes.getCronJobs,
  instantiateAutomationBlueprint: hermes.instantiateAutomationBlueprint
}))

// The view writes jobs into a named profile; pin the scope instead of booting the gateway store.
vi.mock('@/store/profile', async importOriginal => ({
  ...(await importOriginal<Record<string, unknown>>()),
  $profileScope: atom('work')
}))

const { CronView } = await import('./index')

const pluginBlueprint: AutomationBlueprint = {
  appUrl: 'hermes://blueprint/teamtools%3Astandup',
  category: 'work',
  command: '/blueprint teamtools:standup',
  description: 'Weekday summary of what changed in a repo.',
  fields: [
    {
      default: '09:15',
      help: '',
      label: 'What time?',
      name: 'time',
      optional: false,
      options: [],
      strict: true,
      type: 'time'
    }
  ],
  key: 'teamtools:standup',
  plugin: 'teamtools',
  source: 'plugin',
  tags: ['work'],
  title: 'Team standup digest'
}

const builtinBlueprint: AutomationBlueprint = {
  ...pluginBlueprint,
  appUrl: 'hermes://blueprint/morning-brief',
  command: '/blueprint morning-brief',
  key: 'morning-brief',
  plugin: null,
  source: 'builtin',
  title: 'Morning briefing'
}

function renderView() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  return render(
    <QueryClientProvider client={client}>
      <CronView onClose={() => {}} />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  HTMLElement.prototype.scrollIntoView ??= () => undefined
  hermes.getCronJobs.mockResolvedValue([])
  hermes.getAutomationBlueprints.mockResolvedValue({ blueprints: [builtinBlueprint, pluginBlueprint] })
  hermes.instantiateAutomationBlueprint.mockResolvedValue({
    id: 'job-1',
    name: 'Team standup digest',
    prompt: 'Summarize yesterday',
    schedule: { kind: 'cron', expr: '15 9 * * 1-5' }
  } as unknown as CronJob)
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('plugin-registered automation blueprints', () => {
  it('lists the plugin blueprint with its plugin label and instantiates it into the scoped profile', async () => {
    renderView()

    fireEvent.click((await screen.findAllByRole('button', { name: '新建定时任务' }))[0])
    const selector = await screen.findByLabelText('从此开始')
    fireEvent.click(selector)
    fireEvent.keyDown(selector, { key: 'ArrowDown' })
    const option = await screen.findByRole('option', { name: /Team standup digest/ })
    expect(screen.queryByText('Morning briefing')).toBeNull()
    expect(hermes.getAutomationBlueprints).toHaveBeenCalledWith('work')
    fireEvent.click(option)
    fireEvent.click(screen.getByRole('button', { name: '安排任务' }))

    await waitFor(() =>
      expect(hermes.instantiateAutomationBlueprint).toHaveBeenCalledWith(
        { blueprint: 'teamtools:standup', values: { time: '09:15' } },
        'work'
      )
    )
  })
})
