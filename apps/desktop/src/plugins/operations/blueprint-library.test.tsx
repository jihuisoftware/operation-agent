import { type PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeAll, expect, it, vi } from 'vitest'

import { BlueprintLibrary } from './blueprint-library'
import { type BlueprintCatalog, type BlueprintTemplate, moduleLabels, seedBlueprint } from './blueprint-types'
import { adoptBusinessDefaults, selectBusinessSubtype } from './business-config'

vi.mock('@hermes/plugin-sdk', async importOriginal => {
  const sdk = await importOriginal<Record<string, unknown>>()
  const { atom } = await import('nanostores')

  return { ...sdk, host: { state: { requestOwner: atom({ connectionId: 'local', profile: 'one' }) } } }
})
vi.mock('./workbench', () => ({ Workbench: () => <div>内容工作台</div> }))

beforeAll(() => {
  HTMLElement.prototype.scrollIntoView ??= vi.fn()
})

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

const business: BlueprintTemplate = {
  id: 'business-factory',
  kind: 'business',
  title: '工厂与制造企业',
  category: '业务主题',
  description: '展示真实制造能力',
  output: '资料与草稿',
  modules: ['research', 'content', 'report'],
  status: '未加入',
  missing: [],
  times: { research: ['09:00'], content: ['09:40'], report: ['21:00'] },
  subtypes: ['源头工厂', '加工定制'],
  content_directions: ['生产流程', '质检'],
  questions: ['如何确认交期？'],
  defaults: {
    topic: '工厂与制造企业',
    goal: '展示真实生产与交付能力',
    audience: '采购负责人',
    style: '专业务实',
    keywords: ['采购需求', '质量检验']
  }
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

it('selects a business and subtype, then restores edited defaults from a saved draft', async () => {
  const initial = catalog()
  initial.version = 0
  initial.policy.goal = ''
  initial.policy.style = '真实、清楚、具体'
  initial.templates.push(business)

  const rest = vi.fn(async (path: string, options?: any) => {
    if (path === '/blueprints/apply') {
      initial.draft = { policy: options.body.policy, version: 0 }

      return { version: 0, draft: true }
    }

    return initial
  })

  render(
    <BlueprintLibrary
      ctx={{ rest } as unknown as PluginContext}
      owner={{ connectionId: 'local', profile: 'one' }}
      view="blueprints"
    />
  )
  fireEvent.click(await screen.findByRole('button', { name: /工厂与制造企业/ }))
  fireEvent.click(screen.getByRole('button', { name: '使用此业务主题' }))
  expect(rest).toHaveBeenCalledTimes(1)
  expect((screen.getByLabelText('目标受众') as HTMLInputElement).value).toBe('采购负责人')
  expect((screen.getByLabelText('内容风格') as HTMLInputElement).value).toBe('专业务实')
  const selector = screen.getByRole('combobox', { name: '业务子类' })
  fireEvent.click(selector)
  fireEvent.keyDown(selector, { key: 'ArrowDown' })
  fireEvent.click(await screen.findByRole('option', { name: '加工定制' }))
  expect((screen.getByLabelText('运营主题') as HTMLInputElement).value).toBe('工厂与制造企业 · 加工定制')
  fireEvent.change(screen.getByLabelText('运营目标'), { target: { value: '面向服装品牌展示加工能力' } })
  fireEvent.click(screen.getByRole('button', { name: '保存草稿' }))
  fireEvent.click(await screen.findByRole('button', { name: '继续配置' }))
  expect(screen.getByRole('combobox', { name: '业务子类' }).textContent).toContain('加工定制')
  expect((screen.getByLabelText('运营目标') as HTMLInputElement).value).toBe('面向服装品牌展示加工能力')
  expect(initial.draft?.policy).toMatchObject({
    business_theme: business.id,
    business_subtype: '加工定制',
    keywords: ['加工定制 采购需求', '加工定制 质量检验'],
    allowed: initial.policy.allowed,
    knowledge: []
  })
})

it('keeps existing business content until explicitly adopting defaults, without changing permissions or resources', () => {
  const initial = catalog('已有的产品方向')
  initial.policy.style = '我自己的写作风格'
  initial.policy.keywords = ['真实产品型号']
  initial.policy.knowledge = ['已确认的营业时间']
  initial.policy.account_id = 'real-account'
  initial.policy.times.research = ['08:30']
  const seeded = seedBlueprint(initial, business)
  expect(seeded).toMatchObject({
    topic: initial.policy.topic,
    goal: initial.policy.goal,
    style: initial.policy.style,
    keywords: initial.policy.keywords,
    limits: initial.policy.limits,
    allowed: initial.policy.allowed
  })
  const subtype = selectBusinessSubtype(seeded, business, '源头工厂')
  expect(subtype.topic).toBe(initial.policy.topic)
  expect(subtype.keywords).toEqual(initial.policy.keywords)
  const adopted = adoptBusinessDefaults(subtype, business)
  expect(adopted.goal).toBe(business.defaults?.goal)
  expect(adopted.topic).toBe('工厂与制造企业 · 源头工厂')
  expect(adopted).toMatchObject({
    account_id: initial.policy.account_id,
    knowledge: initial.policy.knowledge,
    limits: initial.policy.limits,
    allowed: initial.policy.allowed,
    times: initial.policy.times
  })
  expect(initial.policy.topic).toBe('已有的产品方向')
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

it('explains blocked enable and applies only after correcting and reviewing prerequisites', async () => {
  const initial = catalog('城市步行')
  initial.policy.modules.dm = true
  initial.policy.allowed.dm = true
  initial.policy.account_id = 'test-account'

  const rest = vi.fn(async (path: string, options?: any) => {
    if (path === '/blueprints/preview') {
      return {
        version: 4,
        policy: options.body.policy,
        missing: options.body.policy.knowledge.length ? {} : { dm: ['补充已确认的回复知识'] },
        timeline: [],
        changes: []
      }
    }

    return initial
  })

  render(
    <BlueprintLibrary
      ctx={{ rest } as unknown as PluginContext}
      owner={{ connectionId: 'local', profile: 'one' }}
      view="blueprints"
    />
  )
  fireEvent.click(await screen.findByRole('button', { name: '配置并加入计划' }))
  fireEvent.click(screen.getByRole('button', { name: '下一步：时间与规则' }))
  fireEvent.click(screen.getByRole('button', { name: '改为使用当前扫码登录账号' }))
  expect(screen.queryByLabelText('小红书账号 ID')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '检查与预览' }))
  fireEvent.click(await screen.findByRole('button', { name: '应用并启用' }))
  expect(screen.getByText(/暂不能启用/).textContent).toContain('保存草稿')
  expect(screen.getByText(/补充已确认的回复知识/).textContent).toContain('收到私信处理')
  expect(rest.mock.calls.some(([path]) => path === '/blueprints/apply')).toBe(false)
  expect((screen.getByRole('button', { name: '保存草稿' }) as HTMLButtonElement).disabled).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: '完善时间与规则' }))
  fireEvent.change(screen.getByLabelText('已确认回复知识（每行一条）'), { target: { value: '营业时间为工作日 9:00 至 18:00' } })
  fireEvent.click(screen.getByRole('button', { name: '检查与预览' }))
  fireEvent.click(await screen.findByRole('button', { name: '应用并启用' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/blueprints/apply', expect.objectContaining({
    owner: { connectionId: 'local', profile: 'one' },
    body: expect.objectContaining({
      version: 4,
      mode: 'enable',
      policy: expect.objectContaining({ account_id: '', knowledge: ['营业时间为工作日 9:00 至 18:00'] })
    })
  })))
})

it('prefills newly selected actions while preserving existing permissions, modules and limits', async () => {
  const initial = catalog('城市步行')
  initial.policy.goal = ''
  initial.policy.modules.dm = true
  initial.policy.times.research = ['08:30']
  initial.templates.push({
    id: 'xiaohongshu-daily',
    kind: 'scenario',
    title: '小红书日更',
    category: '推荐场景',
    description: '采集、生产与发布',
    output: '发布结果和日报',
    modules: ['research', 'content', 'publish', 'report'],
    defaults: { goal: '根据来源生成可追溯的内容', style: '自然清晰' },
    times: { research: ['08:30'], content: ['09:40'], publish: ['10:00'], report: ['21:00'] },
    status: '未加入',
    missing: ['选择并授权至少一个对应动作']
  })
  const rest = vi.fn(async () => initial)
  render(
    <BlueprintLibrary
      ctx={{ rest } as unknown as PluginContext}
      owner={{ connectionId: 'local', profile: 'one' }}
      view="blueprints"
    />
  )
  fireEvent.click(await screen.findByRole('button', { name: /小红书日更/ }))
  fireEvent.click(screen.getByRole('button', { name: '使用场景并调整' }))
  expect(rest).toHaveBeenCalledTimes(1)
  expect((screen.getByLabelText('运营目标') as HTMLInputElement).value).toBe('根据来源生成可追溯的内容')
  fireEvent.change(screen.getByLabelText('运营目标'), { target: { value: '我自己的内容目标' } })
  fireEvent.click(screen.getByRole('button', { name: '下一步：时间与规则' }))
  expect(screen.queryByLabelText('小红书账号 ID')).toBeNull()
  expect(screen.getByText(/无需预填账号/)).toBeTruthy()
  const time = screen.getByLabelText('信息采集与选题时间（多个时间用逗号分隔）') as HTMLInputElement
  expect(time.value).toBe('08:30')
  fireEvent.change(time, { target: { value: '08:45,16:00' } })
  expect(screen.getByRole('checkbox', { name: '允许发布图文' }).getAttribute('aria-checked')).toBe('true')
  fireEvent.click(screen.getByRole('button', { name: '保存草稿' }))
  await waitFor(() =>
    expect(rest).toHaveBeenCalledWith(
      '/blueprints/apply',
      expect.objectContaining({
        owner: { connectionId: 'local', profile: 'one' },
        body: expect.objectContaining({
          mode: 'draft',
          policy: expect.objectContaining({
            goal: '我自己的内容目标',
            allowed: { ...initial.policy.allowed, publish: true },
            limits: initial.policy.limits,
            times: expect.objectContaining({ research: ['08:45', '16:00'] }),
            modules: expect.objectContaining({ dm: true, research: true, publish: true })
          })
        })
      })
    )
  )
})

it('applies default modules and authorization to an existing plan only when requested, preserving its limits', async () => {
  const initial = catalog('个人号与个人 IP')
  initial.policy.modules.content = true
  initial.policy.modules.publish = true
  initial.policy.allowed.publish = false
  initial.policy.times.content = ['08:45']
  initial.policy.limits.publish = 0
  const rest = vi.fn(async () => initial)

  render(
    <BlueprintLibrary
      ctx={{ rest } as unknown as PluginContext}
      owner={{ connectionId: 'local', profile: 'one' }}
      view="blueprints"
    />
  )
  fireEvent.click(await screen.findByRole('button', { name: /每日自动运营/ }))
  fireEvent.click(screen.getByRole('button', { name: '配置并加入计划' }))
  fireEvent.click(screen.getByRole('button', { name: '启用默认运营模块与授权' }))
  fireEvent.click(screen.getByRole('button', { name: '下一步：时间与规则' }))

  for (const name of ['允许发布图文', '允许主动评论', '允许评论回复', '允许私信回复']) {
    expect(screen.getByRole('checkbox', { name }).getAttribute('aria-checked')).toBe('true')
  }

  fireEvent.click(screen.getByRole('button', { name: '保存草稿' }))
  await waitFor(() =>
    expect(rest).toHaveBeenCalledWith('/blueprints/apply', expect.objectContaining({
      body: expect.objectContaining({ policy: expect.objectContaining({
        modules: { research: true, content: true, publish: true, comments: true, dm: true, follow: false, report: true },
        allowed: { publish: true, comment: true, reply: true, dm: true, follow: false },
        limits: initial.policy.limits,
        times: initial.policy.times
      }) })
    }))
  )
})
