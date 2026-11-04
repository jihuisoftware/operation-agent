import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { xhsPage } from './page'
import { xhsReady } from './page-ready'

beforeEach(() => {
  vi.stubGlobal('location', new URL('https://www.xiaohongshu.com/user/profile/me'))
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(10)
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.body.innerHTML = '' })

it('recognizes a follower profile link and mutual-follow button without synthetic data attributes', () => {
  document.body.innerHTML = '<div role="dialog"><h2>粉丝</h2><div><a href="https://www.xiaohongshu.com/user/profile/fan">关注者</a><button>互相关注</button></div></div>'
  expect(xhsReady({ phase: 'inventory', payload: { kind: 'follow' } }).ready).toBe(true)
  const result = xhsPage({ operation: 'inventory', payload: { kind: 'follow' } }) as { items: Record<string, unknown>[] }
  expect(result.items).toEqual([expect.objectContaining({ id: 'fan', follows_me: true, already_following: true })])
})

it('opens only the selected real search card and preserves its signed link', () => {
  vi.stubGlobal('location', new URL('https://www.xiaohongshu.com/search_result?keyword=test'))
  document.body.innerHTML = '<section class="note-item"><a href="https://www.xiaohongshu.com/explore/one">封面</a><a id="signed" href="https://www.xiaohongshu.com/explore/one?xsec_token=kept">正文</a></section><section class="note-item"><a href="https://www.xiaohongshu.com/explore/two">其他笔记</a></section>'
  const clicked = vi.fn((event: Event) => event.preventDefault())
  document.querySelector('#signed')!.addEventListener('click', clicked)
  const result = xhsPage({ operation: 'inventory', payload: { kind: 'comment' } }) as { items: { id: string; url: string }[] }
  expect(result.items[0].url).toContain('xsec_token=kept')
  xhsPage({ operation: 'open-note', payload: { kind: 'comment', target: 'note:one' } })
  expect(clicked).toHaveBeenCalledOnce()
})

it('keeps blank notifications unconfirmed and rejects a different note before writing', () => {
  document.body.innerHTML = '<nav>评论和@ 赞和收藏 新增关注</nav>'
  expect(xhsReady({ phase: 'inventory', payload: { kind: 'reply' } }).ready).toBe(false)
  vi.stubGlobal('location', new URL('https://www.xiaohongshu.com/explore/other'))
  document.body.innerHTML = '<div id="detail-desc">其他笔记</div><textarea></textarea><button>发送</button>'
  expect(xhsReady({ phase: 'interaction', payload: { kind: 'comment', target: 'note:wanted' } }).ready).toBe(false)
  expect(() => xhsPage({ operation: 'prepare-interaction', payload: { kind: 'comment', target: 'note:wanted', text: '内容' } })).toThrow('目标不一致')
})
