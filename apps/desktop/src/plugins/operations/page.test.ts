import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { xhsPage } from './page'

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(100)
})
afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

it('ignores offscreen measurement duplicates when selecting an upload tab', () => {
  document.body.innerHTML = '<span id="measure">上传图文</span><div aria-hidden="true"><span>上传图文</span></div><span id="actual">上传图文</span>'
  vi.spyOn(document.querySelector('#measure')!, 'getBoundingClientRect').mockReturnValue({ bottom: -9900, right: -9900 } as DOMRect)
  const clicked = vi.fn()
  document.querySelector('#actual')!.addEventListener('click', clicked)
  xhsPage({ operation: 'click-label', payload: { label: '上传图文' } })
  expect(clicked).toHaveBeenCalledOnce()
})

it('does not treat missing identifiers as candidates', () => {
  document.body.innerHTML = '<div class="comment-item">没有稳定标识</div>'
  expect(() => xhsPage({ operation: 'inventory', payload: { kind: 'reply' } })).toThrow('页面结构')
})

it('preserves rich-text paragraphs and checks words independently of layout whitespace', () => {
  document.body.innerHTML = '<input placeholder="标题"><div contenteditable="true"></div>'
  const payload = { title: '标题', body: '第一段\n\n第二段', asset_ids: [] }
  xhsPage({ operation: 'fill-post', payload })
  const editor = document.querySelector<HTMLElement>('[contenteditable]')!
  expect(Array.from(editor.children, element => element.textContent)).toEqual(['第一段', '', '第二段'])
  Object.defineProperty(editor, 'innerText', { configurable: true, value: '第一段\n第二段' })
  expect(xhsPage({ operation: 'validate-post', payload })).toEqual({ ready: true })
  Object.defineProperty(editor, 'innerText', { value: '第一段\n改过的第二段' })
  expect(() => xhsPage({ operation: 'validate-post', payload })).toThrow('核对不一致')
})

it('does not send a reply when text changed after preparation', () => {
  document.body.innerHTML = '<div data-comment-id="c"><textarea>被改动</textarea><button>发送</button></div>'
  const clicked = vi.fn()
  document.querySelector('button')!.addEventListener('click', clicked)
  expect(() =>
    xhsPage({ operation: 'commit-interaction', payload: { kind: 'reply', target: 'c', text: '批准的回复' } })
  ).toThrow('核对不一致')
  expect(clicked).not.toHaveBeenCalled()
})

it('does not follow someone without an explicit follows-me observation', () => {
  document.body.innerHTML = '<div data-user-id="u"><span>用户简介</span><button>回关</button></div>'
  expect(() => xhsPage({ operation: 'commit-interaction', payload: { kind: 'follow', target: 'u' } })).toThrow(
    '关注状态'
  )
})

it('does not confuse a follower badge with a completed follow-back', () => {
  document.body.innerHTML = '<div data-user-id="u"><span>已关注你</span><button>回关</button></div>'
  expect(xhsPage({ operation: 'interaction-result', payload: { kind: 'follow', target: 'u' } })).toMatchObject({
    state: 'unknown'
  })
  document.querySelector('button')!.textContent = '互相关注'
  expect(xhsPage({ operation: 'interaction-result', payload: { kind: 'follow', target: 'u' } })).toMatchObject({
    state: 'confirmed'
  })
})

it('requires a new visible reply instead of accepting identical old text', () => {
  document.body.innerHTML = '<div class="comment-content">谢谢</div>'
  const payload = { kind: 'comment', text: '谢谢', before_count: 1 }
  expect(xhsPage({ operation: 'interaction-result', payload })).toMatchObject({ state: 'unknown' })
  document.body.insertAdjacentHTML('beforeend', '<div class="comment-content">谢谢</div>')
  expect(xhsPage({ operation: 'interaction-result', payload })).toMatchObject({ state: 'confirmed' })
})
