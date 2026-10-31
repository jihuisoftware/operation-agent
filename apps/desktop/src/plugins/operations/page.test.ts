import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { xhsPage } from './page'

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(100)
})
afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

it('does not treat missing identifiers as candidates', () => {
  document.body.innerHTML = '<div class="comment-item">没有稳定标识</div>'
  expect(() => xhsPage({ operation: 'inventory', payload: { kind: 'reply' } })).toThrow('页面结构')
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
