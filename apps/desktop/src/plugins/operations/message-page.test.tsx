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

it('shows a shared message with its handling topic and keeps handling in that topic', async () => {
  const row = { id: 'shared', kind: 'reply', account: 'acct', text: '开门时间', state: 'manual',
    revision: '1:', created: '2026-11-27T01:00:00Z', read_only: true, owner_topic: '主题甲' }
  const rest = vi.fn(async (path: string) => path === '/messages/shared' ? row : { total: 1, items: [row], next: null })
  render(<MemoryRouter initialEntries={['/interactions?tab=messages']}>
    <SectionPage ctx={{ rest } as unknown as PluginContext} section="interactions" />
  </MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: /主题甲.*开门时间/ }))
  expect(await screen.findByText('此消息由「主题甲」处理，可切换到该主题办理。')).toBeTruthy()
  expect(screen.queryByRole('button', { name: '人工接手' })).toBeNull()
  expect(screen.queryByRole('button', { name: '标记已处理' })).toBeNull()
})

it('offers the three notification sources and filters likes separately from private messages', async () => {
  const rest = vi.fn(async () => ({ total: 0, items: [], next: null }))
  render(<MemoryRouter initialEntries={['/interactions?tab=messages']}>
    <SectionPage ctx={{ rest } as unknown as PluginContext} section="interactions" />
  </MemoryRouter>)
  const source = await screen.findByLabelText('来源')
  expect([...source.querySelectorAll('option')].map(option => option.textContent)).toEqual(['全部', '评论和 @', '赞和收藏', '新增关注'])
  fireEvent.change(source, { target: { value: 'reaction' } })
  await waitFor(() => expect(rest.mock.calls.some(call => String(call).includes('source=reaction'))).toBe(true))
})

it('filters the display independently of the checked sync platforms', async () => {
  const rest = vi.fn(async (path: string) => path.startsWith('/messages?')
    ? { total: 0, items: [], next: null } : { follow: 2, reaction: 1, reply: 0 })
  render(<MemoryRouter initialEntries={['/interactions?tab=messages']}>
    <SectionPage ctx={{ rest } as unknown as PluginContext} section="interactions" />
  </MemoryRouter>)
  fireEvent.change(await screen.findByLabelText('平台'), { target: { value: 'xiaohongshu' } })
  await waitFor(() => expect(rest.mock.calls.some(([path]) => path.includes('platform=xiaohongshu'))).toBe(true))
  fireEvent.click(screen.getByText('拉取平台', { selector: 'summary' }))
  fireEvent.click(screen.getByRole('checkbox', { name: '小红书' }))
  const receive = screen.getByRole('button', { name: '接收平台通知' }) as HTMLButtonElement
  expect(receive.disabled).toBe(true)
  fireEvent.click(screen.getByRole('checkbox', { name: '知乎' }))
  fireEvent.click(receive)
  await screen.findByText(/知乎 · 评论和 @ 0 条/)
  expect(rest.mock.calls.filter(([path]) => path === '/messages/sync-notifications')).toEqual([
    ['/messages/sync-notifications', expect.objectContaining({ body: { platform: 'zhihu' } })]
  ])
})

it('receives both checked platforms even when the first reports an error', async () => {
  const rest = vi.fn(async (path: string, options?: { body: { platform: string } }) => {
    if (path.startsWith('/messages?')) return { total: 0, items: [], next: null }
    if (options?.body.platform === 'xiaohongshu') throw new Error('网页暂不可用')
    return { follow: 0, reaction: 1, reply: 2 }
  })
  render(<MemoryRouter initialEntries={['/interactions?tab=messages']}>
    <SectionPage ctx={{ rest } as unknown as PluginContext} section="interactions" />
  </MemoryRouter>)
  fireEvent.click(await screen.findByText('拉取平台', { selector: 'summary' }))
  fireEvent.click(screen.getByRole('checkbox', { name: '知乎' }))
  fireEvent.click(screen.getByRole('button', { name: '接收平台通知' }))
  await screen.findByText(/小红书接收失败.*知乎 · 评论和 @ 2 条/)
  expect(rest.mock.calls.filter(([path]) => path === '/messages/sync-notifications')
    .map(([, options]) => options?.body.platform)).toEqual(['xiaohongshu', 'zhihu'])
})
