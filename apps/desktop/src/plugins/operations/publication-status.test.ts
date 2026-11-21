import { afterEach, expect, it, vi } from 'vitest'
import { publicationPage } from './publication-page'
import { resolvePublication } from './publication'

const payload = { account_id: 'me', note_id: 'new', content: { title: '测试图文', body: '正文' }, images: ['https://sns.xhscdn.com/image-id!detail_webp'] }
afterEach(() => { document.body.innerHTML = ''; vi.unstubAllGlobals() })
function manager(html: string) {
  vi.stubGlobal('location', new URL('https://creator.xiaohongshu.com/new/note-manager'))
  document.body.innerHTML = html
  return publicationPage({ operation: 'manager', payload }) as { platform: string }
}
it('uses the selected published tab only for the exact uniquely identified note', () => {
  const tab = '<div class="tab-item tab-item--active">已发布（3）</div>'
  expect(manager(`${tab}<article class="note-card" data-note-id="new"><span class="title">测试图文</span></article>`).platform).toBe('published')
  expect(manager(`${tab}<div hidden><article class="note-card" data-note-id="new">测试图文</article></div>`).platform).toBe('unknown')
  expect(manager(`${tab}<article class="note-card" data-note-id="other"><span class="title">测试图文</span></article>`).platform).toBe('unknown')
  expect(manager(`${tab}<article class="note-card" data-note-id="new"><span>审核中</span></article>`).platform).toBe('reviewing')
})
it('joins transformed CDN covers but never overrides a conflicting note identity', () => {
  const card = (id: string) => `<article class="note-card" ${id ? `data-note-id="${id}"` : ''}><span class="note-card__title">测试图文</span><img src="https://sns.xhscdn.com/image-id!cover_jpg"><span>已发布</span></article>`
  expect(manager(card('')).platform).toBe('published')
  expect(manager(card('other')).platform).toBe('unknown')
  expect(manager(card('') + card('')).platform).toBe('unknown')
})
it('waits for platform status instead of accepting the first loaded unknown card', async () => {
  let reads = 0
  const read = vi.fn(async (operation: string) => operation === 'inspect' ? {
    ready: true, id: 'new', url: 'https://www.xiaohongshu.com/explore/new', platform: 'unknown',
    checks: { author: true, title: true, body: true }, images: payload.images, actual: {}
  } : operation === 'manager_select_published' ? { selected: true } : { ready: true, platform: ++reads === 1 ? 'unknown' : 'published' })
  const result = await resolvePublication({ read, navigate: vi.fn(), images: async () => ({ state: 'incomplete', evidence: 'CDN 转码' }),
    trace: { step: async (_name: string, fn: () => Promise<unknown>) => fn() } as never, sleep: async () => {} }, payload,
    { state: 'submitted', url: 'https://www.xiaohongshu.com/explore/new', error: '旧窗口中断', error_code: 'WINDOW_CLOSED' })
  expect(reads).toBe(2)
  expect(result.publication).toEqual({ execution: 'verified', platform: 'published', content: 'incomplete' })
  expect(result.state).toBe('submitted')
  expect(result).not.toHaveProperty('error')
  expect(result).not.toHaveProperty('error_code')
})

it('only selects the published list filter and never clicks matching note text', () => {
  manager('<div role="tab" id="published">已发布</div><article class="note-card"><span>已发布</span></article>')
  const tab = vi.fn(), note = vi.fn()
  document.querySelector('#published')!.addEventListener('click', tab)
  document.querySelector('article span')!.addEventListener('click', note)
  expect(publicationPage({ operation: 'manager_select_published', payload })).toEqual({ selected: true })
  expect(tab).toHaveBeenCalledOnce()
  expect(note).not.toHaveBeenCalled()
})
