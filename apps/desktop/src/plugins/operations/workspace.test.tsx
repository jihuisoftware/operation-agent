import { host, type PluginContext } from '@hermes/plugin-sdk'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { WritableAtom } from 'nanostores'
import { useEffect, useState } from 'react'
import { MemoryRouter } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'

import { ExecutionPlanLink, WorkspaceManagement } from './workspace-management'
import { WorkspacePage } from './workspace-page'
import { WorkspaceNavigationGuard } from './workspace-navigation-guard'
import { $loginActivity } from './login-activity'
import { WorkspacePicker } from './workspace-picker'
import { $workspaceDirty, $workspaces, chooseScope, ownerKey, scopedContext, scopeKey } from './workspace-state'

vi.mock('@hermes/plugin-sdk', async importOriginal => {
  const sdk = await importOriginal<Record<string, unknown>>()
  const { atom } = await import('nanostores')
  const { useStore } = await import('@nanostores/react')

  return { ...sdk, host: { navigate: vi.fn(), state: { requestOwner: atom({ connectionId: 'local', profile: 'test' }) } }, useValue: useStore }
})
const owner = { connectionId: 'local', profile: 'test' }
const requestOwner = host.state.requestOwner as WritableAtom<typeof owner>
const first = { business_id: 'a', topic_id: 'one' }, second = { business_id: 'b', topic_id: 'two' }

const catalog = {
  businesses: [{ id: 'a', name: '甲业务', category: '', archived: 0, paused: 0, account: 'aa' }, { id: 'b', name: '乙业务', category: '', archived: 0, paused: 0, account: 'bb' }],
  topics: [{ id: 'one', business_id: 'a', name: '同名主题', archived: 0 }, { id: 'two', business_id: 'b', name: '同名主题', archived: 0 }],
  accounts: [{ id: 'aa', identity: '', conflict: '', held: 0 }, { id: 'bb', identity: '', conflict: '', held: 0 }], paused: false
}

afterEach(() => { cleanup(); $workspaces.set({}); $workspaceDirty.set({}); requestOwner.set(owner); vi.clearAllMocks() })

function Probe({ ctx }: { ctx: PluginContext }) {
  const [label, setLabel] = useState('加载中')
  useEffect(() => {
    let disposed = false
    void ctx.rest<{ label: string }>('/state').then(value => { if (!disposed) { setLabel(value.label) } })

    return () => { disposed = true }
  }, [ctx])

  return <p>{label}</p>
}

it('binds each request to immutable Profile, business and topic ownership', async () => {
  const rest = vi.fn(async () => ({}))
  const ctx = { rest } as unknown as PluginContext
  const a = scopedContext(ctx, owner, first), b = scopedContext(ctx, owner, second)
  await a.rest('/sources?cursor=2')
  await b.rest('/sources?cursor=2')
  expect(rest.mock.calls).toEqual([
    ['/sources?cursor=2&business_id=a&topic_id=one', { owner }],
    ['/sources?cursor=2&business_id=b&topic_id=two', { owner }]
  ])
})

it('discards a late page response after switching and resolves an explicitly scoped link', async () => {
  let resolveOld!: (value: { label: string }) => void

  const rest = vi.fn(async (path: string) => {
    if (path === '/workspaces') { return catalog }

    if (path.startsWith('/state') && path.includes('topic_id=one')) { return new Promise(resolve => { resolveOld = resolve }) }

    if (path.startsWith('/state')) { return { label: '乙主题资料' } }

    return {}
  })

  const ctx = { rest } as unknown as PluginContext
  render(<MemoryRouter><WorkspacePage ctx={ctx}>{scoped => <Probe ctx={scoped} />}</WorkspacePage></MemoryRouter>)
  await waitFor(() => expect(resolveOld).toBeTypeOf('function'))
  act(() => chooseScope(owner, second))
  expect(await screen.findByText('乙主题资料')).toBeTruthy()
  await act(async () => resolveOld({ label: '甲主题旧响应' }))
  expect(screen.queryByText('甲主题旧响应')).toBeNull()
  expect(rest.mock.calls.some(([path]) => path === '/policy?business_id=b&topic_id=two')).toBe(true)
})

it('requires discarding unsaved configuration before changing business', async () => {
  const rest = vi.fn(async (path: string) => path === '/workspaces' ? catalog : {})
  const ctx = { rest } as unknown as PluginContext
  render(<><WorkspacePicker ctx={ctx} /><WorkspaceNavigationGuard /></>)
  const picker = await screen.findByRole('button', { name: /当前业务与主题，甲业务/ })
  act(() => $workspaceDirty.set({ [scopeKey(owner, first)]: true }))
  fireEvent.keyDown(picker, { key: 'ArrowDown' })
  fireEvent.click(await screen.findByRole('menuitem', { name: '乙业务 / 同名主题' }))
  expect($workspaces.get()[ownerKey(host.state.requestOwner.get())].selected).toEqual(first)
  fireEvent.click(screen.getByRole('button', { name: '放弃修改并切换' }))
  expect($workspaces.get()[ownerKey(owner)].selected).toEqual(second)
})

it('opens the directory from the scope picker without changing the current topic', async () => {
  const ctx = { rest: vi.fn(async () => catalog) } as unknown as PluginContext
  render(<WorkspacePicker ctx={ctx} />)
  fireEvent.keyDown(await screen.findByRole('button', { name: /当前业务与主题，甲业务/ }), { key: 'ArrowDown' })
  fireEvent.click(await screen.findByRole('menuitem', { name: '管理业务与主题' }))
  expect(host.navigate).toHaveBeenCalledWith('/operations/workspaces')
  expect($workspaces.get()[ownerKey(owner)].selected).toEqual(first)
})

it('only shows confirmed login warnings for the selected business', async () => {
  const rest = vi.fn(async (path: string) => {
    if (path === '/workspaces') return catalog
    if (path.startsWith('/platforms?')) return { platforms: [{ name: '小红书',
      state: path.includes('business_id=a') ? 'logged_out' : 'unchecked' }] }
    return {}
  })
  render(<WorkspacePicker ctx={{ rest } as unknown as PluginContext} />)
  await waitFor(() => expect($loginActivity.get().attention).toBe('小红书：需要登录'))
  fireEvent.keyDown(screen.getByRole('button', { name: /当前业务与主题，甲业务/ }), { key: 'ArrowDown' })
  fireEvent.click(await screen.findByRole('menuitem', { name: '乙业务 / 同名主题' }))
  await waitFor(() => expect(rest.mock.calls.some(([path]) => path.startsWith('/platforms?business_id=b&topic_id=two'))).toBe(true))
  expect($loginActivity.get().attention).toBeFalsy()
})

it('lets a reset workspace recover from a stale record URL without loading old data', async () => {
  const rest = vi.fn(async (path: string) => {
    if (path === '/workspaces') { return catalog }

    if (path.startsWith('/policy?business_id=deleted')) { throw new Error('业务或主题不存在') }

    if (path.startsWith('/state')) { return { label: '新的空白业务' } }

    return {}
  })

  const ctx = { rest } as unknown as PluginContext
  render(<MemoryRouter initialEntries={['/?business_id=deleted&topic_id=deleted']}><WorkspacePage ctx={ctx}>{scoped => <Probe ctx={scoped} />}</WorkspacePage></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: '返回当前业务' }))
  expect(await screen.findByText('新的空白业务')).toBeTruthy()
  expect(rest.mock.calls.filter(([path]) => path.startsWith('/state')).every(([path]) => path.includes('business_id=a&topic_id=one'))).toBe(true)
})

it('drops the previous Profile URL scope when switching Profiles', async () => {
  const rest = vi.fn(async (path: string, options?: { owner?: { profile?: string } }) => {
    if (path === '/workspaces') { return catalog }

    if (path.startsWith('/state')) { return { label: `${options?.owner?.profile}:${path}` } }

    return {}
  })

  const ctx = { rest } as unknown as PluginContext
  render(<MemoryRouter initialEntries={['/?business_id=b&topic_id=two']}><WorkspacePage ctx={ctx}>{scoped => <Probe ctx={scoped} />}</WorkspacePage></MemoryRouter>)
  await screen.findByText('test:/state?business_id=b&topic_id=two')
  act(() => requestOwner.set({ connectionId: 'local', profile: 'second' }))
  await screen.findByText('second:/state?business_id=a&topic_id=one')
  expect(rest.mock.calls.some(([path, options]) => path === '/policy?business_id=b&topic_id=two' && options?.owner?.profile === 'second')).toBe(false)
})

it('browses another business without selecting it and confirms before creating a copy', async () => {
  const rest = vi.fn(async (path: string, options?: { method?: string }) => {
    if (path === '/workspaces/summary') return { items: [] }
    if (options?.method === 'POST') return { business_id: 'b', topic_id: 'new' }
    return catalog
  })
  const ctx = { rest } as unknown as PluginContext
  render(<MemoryRouter><WorkspaceManagement ctx={ctx} /><WorkspaceNavigationGuard /></MemoryRouter>)
  fireEvent.change(await screen.findByLabelText('搜索业务或主题'), { target: { value: '乙' } })
  expect(screen.queryByRole('heading', { name: '甲业务' })).toBeNull()
  expect($workspaces.get()[ownerKey(owner)].selected).toEqual(first)
  fireEvent.click(screen.getByText('主题管理'))
  fireEvent.click(screen.getByRole('button', { name: '复制配置为新主题' }))
  fireEvent.change(screen.getByLabelText('复制配置为新主题名称'), { target: { value: '新方向' } })
  act(() => $workspaceDirty.set({ [scopeKey(owner, first)]: true }))
  fireEvent.click(screen.getByRole('button', { name: '确认复制配置为新主题' }))
  fireEvent.click(screen.getByRole('button', { name: '继续编辑' }))
  expect(rest.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0)
  expect($workspaces.get()[ownerKey(owner)].selected).toEqual(first)
  fireEvent.click(screen.getByRole('button', { name: '确认复制配置为新主题' }))
  fireEvent.click(screen.getByRole('button', { name: '放弃修改并切换' }))
  await waitFor(() => expect(host.navigate).toHaveBeenCalledWith('/operations/workspaces?view=plan&business_id=b&topic_id=new'))
  expect(rest).toHaveBeenCalledWith('/workspaces', { owner, method: 'POST', body: { action: 'create', name: '新方向', business_id: 'b', copy_topic: 'two' } })
})

it('opens archived topics as read-only and links their history with explicit ownership', async () => {
  const rest = vi.fn(async (path: string) => {
    if (path === '/workspaces') return { ...catalog, businesses: catalog.businesses.map(b => ({ ...b, archived: Number(b.id === 'b') })) }
    if (path.startsWith('/blueprints?')) return { templates: [], policy: { goal: '归档前的目标', modules: {}, times: {} } }
    return {}
  })
  const ctx = { rest } as unknown as PluginContext
  render(<MemoryRouter initialEntries={['/operations/workspaces?view=plan&business_id=b&topic_id=two']}>
    <WorkspaceManagement ctx={ctx} /></MemoryRouter>)
  expect(await screen.findByText('归档前的目标')).toBeTruthy()
  expect($workspaces.get()[ownerKey(owner)].selected).toEqual(second)
  expect(screen.queryByRole('button', { name: '保存设置' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '查看运营历史' }))
  expect(host.navigate).toHaveBeenCalledWith('/cron?tab=history&historyView=operations.ledger&business_id=b&topic_id=two')
})

it.each(['business_id=a', 'business_id=&topic_id=', 'business_id=a&topic_id=two'])('rejects invalid plan ownership %s before loading an editor', async query => {
  const rest = vi.fn(async (path: string) => {
    if (path === '/workspaces') return catalog
    throw new Error('归属不匹配')
  })
  render(<MemoryRouter initialEntries={['/operations/workspaces?view=plan&' + query]}>
    <WorkspaceManagement ctx={{ rest } as unknown as PluginContext} /></MemoryRouter>)
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(rest.mock.calls.some(([path]) => path.startsWith('/blueprints'))).toBe(false)
  expect($workspaces.get()[ownerKey(owner)].selected).toEqual(first)
})

it('uses the ownership saved with a historical execution even when a different topic is selected', () => {
  $workspaces.set({ [ownerKey(owner)]: { selected: first, catalog } })
  const view = render(<ExecutionPlanLink owner={owner} context={{ ...second, topic: '历史主题' }} />)
  fireEvent.click(screen.getByRole('button', { name: /历史主题/ }))
  expect(host.navigate).toHaveBeenCalledWith('/operations/workspaces?view=plan&business_id=b&topic_id=two')
  view.rerender(<ExecutionPlanLink owner={owner} context={{ topic: '只有名称' }} />)
  expect(screen.queryByRole('button')).toBeNull()
  view.rerender(<ExecutionPlanLink owner={{ ...owner, profile: 'other' }} context={second} />)
  expect(screen.queryByRole('button')).toBeNull()
})
