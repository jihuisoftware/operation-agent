import { host, type PluginContext } from '@hermes/plugin-sdk'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { WritableAtom } from 'nanostores'
import { useEffect, useState } from 'react'
import { MemoryRouter } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'

import { WorkspacePage } from './workspace-page'
import { WorkspacePicker } from './workspace-picker'
import { $workspaceDirty, $workspaces, chooseScope, ownerKey, scopedContext, scopeKey } from './workspace-state'

vi.mock('@hermes/plugin-sdk', async importOriginal => {
  const sdk = await importOriginal<Record<string, unknown>>()
  const { atom } = await import('nanostores')
  const { useStore } = await import('@nanostores/react')

  return { ...sdk, host: { state: { requestOwner: atom({ connectionId: 'local', profile: 'test' }) } }, useValue: useStore }
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
  render(<WorkspacePicker ctx={ctx} />)
  await screen.findByRole('combobox', { name: '业务空间' })
  act(() => $workspaceDirty.set({ [scopeKey(owner, first)]: true }))
  fireEvent.change(screen.getByRole('combobox', { name: '业务空间' }), { target: { value: 'b' } })
  expect($workspaces.get()[ownerKey(host.state.requestOwner.get())].selected).toEqual(first)
  fireEvent.click(screen.getByRole('button', { name: '放弃修改并切换' }))
  expect($workspaces.get()[ownerKey(owner)].selected).toEqual(second)
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
