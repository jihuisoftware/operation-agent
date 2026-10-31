import { type PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { BlueprintLibrary } from './blueprint-library'
import { type BlueprintCatalog, moduleLabels } from './blueprint-types'

vi.mock('@hermes/plugin-sdk', async importOriginal => {
  const sdk = await importOriginal<Record<string, unknown>>()
  const { atom } = await import('nanostores')

  return { ...sdk, host: { state: { requestOwner: atom({ connectionId: 'local', profile: 'one' }) } } }
})
vi.mock('./workbench', () => ({ Workbench: () => <div>内容工作台</div> }))

function catalog(topic = ''): BlueprintCatalog {
  const modules = Object.fromEntries(Object.keys(moduleLabels).map(m => [m, false]))

  return {
    version: 4,
    online: false,
    next_at: null,
    draft: null,
    assets: [],
    timeline: [],
    policy: {
      schema_version: 2,
      modules,
      topic,
      goal: '整理可追溯资料',
      enabled: false,
      paused: false,
      audience: '',
      brand: '',
      style: '',
      account_id: '',
      timezone: 'Asia/Shanghai',
      deadline: '',
      priority: 1,
      model_calls: 10,
      sources: [],
      rss_sources: [],
      keywords: [],
      knowledge: [],
      follow_terms: [],
      allowed: { publish: false, comment: false, reply: false, dm: false, follow: false },
      limits: { source: 3, publish: 1, comment: 2, reply: 2, dm: 1, follow: 1 },
      times: Object.fromEntries(Object.keys(modules).map(m => [m, ['09:00']]))
    },
    templates: [
      { id: 'daily', title: '每日自动运营', modules: ['research', 'content', 'report'] },
      ...Object.entries(moduleLabels).map(([id, title]) => ({ id, title, modules: [id] }))
    ].map(t => ({
      ...t,
      category: '运营',
      description: '根据目标执行',
      output: '执行记录',
      status: '未加入',
      missing: [],
      times: {}
    }))
  }
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

it('selecting a blueprint does not run it; draft and explicit enable retain conservative defaults and version', async () => {
  const initial = catalog('城市步行')

  const rest = vi.fn(async (path: string, options?: any) => {
    if (path === '/blueprints/preview') {
      return { policy: options.body.policy, version: 4, missing: {}, timeline: [], changes: [] }
    }

    if (path === '/blueprints/apply') {
      return { version: 5 }
    }

    return initial
  })

  const ctx = { rest } as unknown as PluginContext
  render(<BlueprintLibrary ctx={ctx} owner={{ connectionId: 'local', profile: 'one' }} view="blueprints" />)
  fireEvent.click(await screen.findByRole('button', { name: '配置并加入计划' }))
  expect((screen.getByLabelText('运营主题') as HTMLInputElement).value).toBe('城市步行')

  for (const [module, label] of Object.entries(moduleLabels)) {
    expect(screen.getByRole('checkbox', { name: label }).getAttribute('aria-checked')).toBe(
      String(['research', 'content', 'report'].includes(module))
    )
  }

  expect(rest.mock.calls.some(([path]) => path === '/blueprints/apply')).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: '保存草稿' }))
  await waitFor(() =>
    expect(rest).toHaveBeenCalledWith(
      '/blueprints/apply',
      expect.objectContaining({
        owner: { connectionId: 'local', profile: 'one' },
        body: expect.objectContaining({
          version: 4,
          mode: 'draft',
          policy: expect.objectContaining({ limits: initial.policy.limits, allowed: initial.policy.allowed })
        })
      })
    )
  )
  await screen.findByRole('status')
  fireEvent.click(screen.getByRole('button', { name: '配置并加入计划' }))
  fireEvent.click(screen.getByRole('button', { name: '下一步：时间与规则' }))
  expect(screen.queryByLabelText('小红书账号 ID')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '检查与预览' }))
  fireEvent.click(await screen.findByRole('button', { name: '应用并启用' }))
  await waitFor(() =>
    expect(rest).toHaveBeenCalledWith(
      '/blueprints/apply',
      expect.objectContaining({ body: expect.objectContaining({ mode: 'enable' }) })
    )
  )
})

it('changing Profile discards an unsaved form and routes future submissions to its new owner', async () => {
  const rest = vi.fn(async (_path: string, options?: any) => catalog(options.owner.profile))
  const ctx = { rest } as unknown as PluginContext

  const { rerender } = render(
    <BlueprintLibrary ctx={ctx} owner={{ connectionId: 'local', profile: 'one' }} view="blueprints" />
  )

  fireEvent.click(await screen.findByRole('button', { name: '配置并加入计划' }))
  fireEvent.change(screen.getByLabelText('运营主题'), { target: { value: '不可泄漏的草稿' } })
  rerender(<BlueprintLibrary ctx={ctx} owner={{ connectionId: 'remote', profile: 'two' }} view="blueprints" />)
  fireEvent.click(await screen.findByRole('button', { name: '配置并加入计划' }))
  expect((screen.getByLabelText('运营主题') as HTMLInputElement).value).toBe('two')
  fireEvent.click(screen.getByRole('button', { name: '保存草稿' }))
  await waitFor(() =>
    expect(rest).toHaveBeenCalledWith(
      '/blueprints/apply',
      expect.objectContaining({
        owner: { connectionId: 'remote', profile: 'two' },
        body: expect.objectContaining({ policy: expect.objectContaining({ topic: 'two' }) })
      })
    )
  )
})

it('missing prerequisites prevent enabling while allowing a draft', async () => {
  const rest = vi.fn(async (path: string) =>
    path === '/blueprints/preview'
      ? { version: 4, policy: catalog().policy, missing: { dm: ['补充已确认的回复知识'] }, timeline: [], changes: [] }
      : catalog()
  )

  render(
    <BlueprintLibrary
      ctx={{ rest } as unknown as PluginContext}
      owner={{ connectionId: 'local', profile: 'one' }}
      view="blueprints"
    />
  )
  fireEvent.click(await screen.findByRole('button', { name: '配置并加入计划' }))
  fireEvent.click(screen.getByRole('button', { name: '下一步：时间与规则' }))
  fireEvent.click(screen.getByRole('button', { name: '检查与预览' }))
  expect(((await screen.findByRole('button', { name: '应用并启用' })) as HTMLButtonElement).disabled).toBe(true)
  expect(screen.getByRole('alert').textContent).toContain('补充已确认的回复知识')
  expect((screen.getByRole('button', { name: '保存草稿' }) as HTMLButtonElement).disabled).toBe(false)
})
