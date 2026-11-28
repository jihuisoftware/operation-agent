import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'
import { SectionPage } from './section-page'

afterEach(cleanup)
function Address() {
  return <output aria-label="地址">{useLocation().search}</output>
}
it.each([
  ['inbox', 'state', 'attention'],
  ['reply', 'source', 'reply'],
  ['dm', 'source', 'dm'],
  ['follow', 'source', 'follow']
])('opens legacy %s at the matching filter and scope', async (old, key, value) => {
  const ctx = { rest: vi.fn(async () => ({ total: 0, items: [], next: null })) } as unknown as PluginContext
  render(
    <MemoryRouter initialEntries={['/interactions?tab=' + old + '&business_id=b&topic_id=t']}>
      <SectionPage ctx={ctx} section="interactions" />
      <Address />
    </MemoryRouter>
  )
  await screen.findByText('当前没有符合条件的消息。')
  const query = new URLSearchParams(screen.getByLabelText('地址').textContent!)
  expect(Object.fromEntries(query)).toMatchObject({ tab: 'messages', [key]: value, business_id: 'b', topic_id: 't' })
})

it('takes a message using its displayed revision and keeps local handling separate from sending', async () => {
  let state = 'manual'
  const row = () => ({
    id: 'msg',
    kind: 'dm',
    account: 'me',
    text: '有货吗',
    reason: '等待人工',
    state,
    revision: state === 'manual' ? '1:' : '2:',
    created: '2026-11-26T01:00:00Z'
  })
  const rest = vi.fn(async (path: string, options?: { method?: string }) => {
    if (options?.method === 'POST') {
      state = 'working'
      return { ok: true }
    }
    if (path === '/messages/msg') return row()
    return { total: 1, items: [row()], next: null }
  })
  render(
    <MemoryRouter initialEntries={['/interactions?tab=messages&record=msg']}>
      <SectionPage ctx={{ rest } as unknown as PluginContext} section="interactions" />
    </MemoryRouter>
  )
  fireEvent.click(await screen.findByRole('button', { name: '人工接手' }))
  await waitFor(() =>
    expect(rest).toHaveBeenCalledWith(
      '/messages/msg',
      expect.objectContaining({ method: 'POST', body: { operation: 'take', revision: '1:', target_topic: '' } })
    )
  )
  expect(await screen.findByText(/私信 · 人工处理中/)).toBeTruthy()
})

it('redirects the former review tab to scoped task history and retains its selected action', async () => {
  const { Route, Routes } = await import('react-router')
  const ctx = { rest: vi.fn() } as unknown as PluginContext
  render(<MemoryRouter initialEntries={['/interactions?tab=unverified&business_id=b&topic_id=t&action=a']}>
    <Routes><Route path="/interactions" element={<SectionPage ctx={ctx} section="interactions" />} />
      <Route path="/cron" element={<Address />} /></Routes></MemoryRouter>)
  const search = new URLSearchParams((await screen.findByLabelText('地址')).textContent!)
  expect(Object.fromEntries(search)).toMatchObject({tab:'history',historyView:'operations.unverified',business_id:'b',topic_id:'t',record:'a'})
  expect(ctx.rest).not.toHaveBeenCalled()
})

it('shows why operator follow is disabled while ignoring stays available for receive-only notices', async () => {
  const row = {id:'fan',kind:'follow',target:'u',account:'me',state:'manual',revision:'1:',text:'简介',created:'2026-11-26T01:00:00Z',
    matching_terms:[],follow_disabled_reason:'该动作未授权',follows_me:true}
  const rest = vi.fn(async (path:string, options?: {method?:string}) => options?.method === 'POST' ? {ok:true} :
    path === '/messages/fan' ? row : {total:1,items:[row],next:null})
  render(<MemoryRouter initialEntries={['/interactions?tab=messages&source=follow&record=fan']}>
    <SectionPage ctx={{rest} as unknown as PluginContext} section="interactions"/></MemoryRouter>)
  expect((await screen.findByRole('button',{name:'按规则回关'}) as HTMLButtonElement).disabled).toBe(true)
  expect(screen.getByText('该动作未授权')).toBeTruthy()
  fireEvent.click(screen.getByRole('button',{name:'忽略'}))
  await waitFor(()=>expect(rest).toHaveBeenCalledWith('/messages/fan',expect.objectContaining({method:'POST',body:{operation:'ignore',revision:'1:',target_topic:''}})))
})
