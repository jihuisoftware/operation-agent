import { type PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, beforeAll, expect, it, vi } from 'vitest'

import { initialPlan, selectMode } from './plan-config'
import { PlanEditor } from './plan-editor'
import { business, catalog } from './plan-fixtures'
import { PlanForm } from './plan-form'

vi.mock('@hermes/plugin-sdk', async importOriginal => {
  const sdk = await importOriginal<Record<string, unknown>>()
  const { atom } = await import('nanostores')

  return {
    ...sdk,
    host: {
      state: { model: atom(''), requestOwner: atom({ connectionId: 'local', profile: 'one' }) },
      navigate: vi.fn()
    }
  }
})
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})
beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false
  Element.prototype.setPointerCapture ??= () => undefined
  Element.prototype.releasePointerCapture ??= () => undefined
  Element.prototype.scrollIntoView ??= () => undefined
})
const owner = { connectionId: 'local', profile: 'one' }

it('leaves custom topics empty with guidance and preserves manually entered topics when choosing a business', async () => {
  const initial = catalog()
  initial.templates.push(business)

  function Harness() {
    const [policy, setPolicy] = useState(initial.policy)

    return <PlanForm catalog={initial} change={setPolicy} policy={policy} />
  }

  async function choose(label: string, option: string) {
    fireEvent.keyDown(screen.getByRole('combobox', { name: label }), { key: 'ArrowDown' })
    fireEvent.click(await screen.findByRole('option', { name: option }))
  }

  render(<Harness />)
  await choose('运营场景', business.title)
  expect(screen.getByRole('combobox', { name: '主题名称' }).textContent).toBe('请选择')
  await choose('主题名称', '生产流程')
  await choose('主题名称', '自定义／手动添加')
  const input = screen.getByLabelText('自定义主题名称') as HTMLInputElement
  expect(input.value).toBe('')
  expect(input.placeholder).toBe('填写你想运营的具体方向，例如：小户型收纳、机械零件加工')
  fireEvent.change(input, { target: { value: '精密零件加工' } })
  await choose('运营场景', '请选择')
  await choose('运营场景', business.title)
  expect((screen.getByLabelText('自定义主题名称') as HTMLInputElement).value).toBe('精密零件加工')
})

it('starts from one page without account prerequisites and double click shares the request', async () => {
  const initial = catalog('机械零件加工')
  initial.version = 0
  initial.model_ready = false
  initial.policy.allowed = { publish: true, comment: true, reply: true, dm: true, follow: false }

  const rest = vi.fn(async (path: string, options?: any) => {
    if (path === '/quick-start') {
      return { run: null, steps: [] }
    }

    if (path === '/blueprints/preview') {
      return {
        ...options.body,
        changes: [],
        blocking: [],
        readiness: {
          publish: { selected: true, ready: false, reasons: ['登录账号', '上传获授权图片'], action: '/accounts' }
        }
      }
    }

    return initial
  })

  render(<PlanEditor ctx={{ rest } as unknown as PluginContext} owner={owner} />)
  expect(await screen.findByRole('button', { name: '连接模型' })).toBeTruthy()
  const method = screen.getByRole('combobox', { name: '发布方式' })
  expect(method.textContent).toBe('普通发布')
  fireEvent.keyDown(method, { key: 'ArrowDown' })
  fireEvent.click(await screen.findByRole('option', { name: 'computer_use 发布' }))
  const start = screen.getByRole('button', { name: '开始运营' })
  await waitFor(() => expect(start.hasAttribute('disabled')).toBe(false))
  expect(screen.getByText(/上传获授权图片/)).toBeTruthy()
  fireEvent.click(start)
  fireEvent.click(start)
  await screen.findByText(/首轮已安排/)
  const calls = rest.mock.calls.filter(([path, options]) => path === '/quick-start' && options?.method === 'POST')
  expect(calls).toHaveLength(1)
  const request = calls[0][1]
  expect(request.owner).toEqual(owner)
  expect(request.body.request_id).toBeTruthy()
  expect(request.body).toMatchObject({
    start: true,
    version: 0,
    policy: { publish_method: 'computer_use', modules: { analytics: true, industry: true, publish: true, follow: false }, limits: { source: 3 } }
  })
})

it('simple and detailed edits preserve saved values, and Profile switching drops the old draft', async () => {
  const initial = catalog('已保存主题')
  initial.policy.modules.research = true
  initial.policy.knowledge = ['真实知识']
  initial.policy.rss_sources = ['https://example.org/feed']

  const rest = vi.fn(async (path: string, options?: any) => {
    if (path === '/quick-start') {
      return { run: null, steps: [] }
    }

    if (path === '/blueprints/preview') {
      return {
        ...options.body,
        changes: [{ field: 'topic', before: '已保存主题', after: options.body.policy.topic }],
        blocking: [],
        readiness: {}
      }
    }

    return {
      ...initial,
      policy: { ...initial.policy, topic: options?.owner.profile === 'two' ? '另一份主题' : '已保存主题' }
    }
  })

  const ctx = { rest } as unknown as PluginContext
  const view = render(<PlanEditor ctx={ctx} owner={owner} />)
  await screen.findByLabelText('自定义主题名称')
  fireEvent.change(screen.getByLabelText('自定义主题名称'), { target: { value: '修改主题' } })
  const save = screen.getByRole('button', { name: '保存设置' })
  await waitFor(() => expect(save.hasAttribute('disabled')).toBe(false))
  fireEvent.click(save)
  await screen.findByText(/将更新以下已保存配置/)
  fireEvent.click(save)
  await screen.findByText(/已保存，可继续/)
  const sent = rest.mock.calls.find(([path, options]) => path === '/quick-start' && options?.method === 'POST')![1]
  expect(sent.body.policy).toMatchObject({
    topic: '修改主题',
    knowledge: ['真实知识'],
    rss_sources: ['https://example.org/feed'],
    limits: { source: 3 },
    allowed: initial.policy.allowed
  })
  view.rerender(<PlanEditor ctx={ctx} owner={{ ...owner, profile: 'two' }} />)
  await waitFor(() => expect((screen.getByLabelText('自定义主题名称') as HTMLInputElement).value).toBe('另一份主题'))
  expect(screen.queryByText(/将更新以下已保存配置/)).toBeNull()
})

it('never reapplies defaults or increases permissions when opening an old plan', () => {
  const old = catalog('特定主题')
  old.policy.modules.research = true
  old.policy.knowledge = ['业务事实']
  expect(initialPlan(old)).toEqual(old.policy)
  const changed = selectMode(initialPlan(old), 'automatic')
  expect(changed.allowed).toEqual(old.policy.allowed)
  expect(changed.limits).toEqual(old.policy.limits)
  expect(changed.knowledge).toEqual(['业务事实'])
})

it.each([true, null])('does not prompt to connect based on an empty chat selection (backend %s)', ready => {
  const initial = catalog()
  initial.model_ready = ready
  render(<PlanForm catalog={initial} change={vi.fn()} policy={initial.policy} />)
  expect(screen.queryByRole('button', { name: '连接模型' })).toBeNull()
})
