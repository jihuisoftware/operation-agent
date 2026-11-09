import { expect, it, vi } from 'vitest'

import { installPublishEntry } from './publish-entry'

function fixture(url = 'https://www.xiaohongshu.com/explore') {
  const page = document.implementation.createHTMLDocument()
  const listen = vi.spyOn(page, 'addEventListener')
  const navigate = vi.fn()
  installPublishEntry(page, url, navigate)

  const click = (html: string, trusted = true) => {
    page.body.innerHTML = html

    const event = {
      target: page.body.querySelector('span'), isTrusted: trusted, button: 0,
      preventDefault: vi.fn(), stopImmediatePropagation: vi.fn()
    }

    const listener = listen.mock.calls.find(([type]) => type === 'click')?.[1] as EventListener | undefined
    listener?.(event as unknown as Event)

    return event
  }

  return { page, listen, navigate, click }
}

it('routes a trusted plus or creator-link click in place, including controls rendered later', () => {
  const f = fixture()
  installPublishEntry(f.page, 'https://www.xiaohongshu.com/explore', f.navigate)
  expect(f.listen).toHaveBeenCalledOnce()
  const plus = f.click('<button class="publish-btn"><svg></svg><span>＋</span></button>')
  expect(plus.preventDefault).toHaveBeenCalledOnce()
  expect(plus.stopImmediatePropagation).toHaveBeenCalledOnce()
  f.click('<a target="_blank" href="https://creator.xiaohongshu.com/publish/publish"><span>发布</span></a>')
  expect(f.navigate.mock.calls).toEqual([
    ['https://creator.xiaohongshu.com/publish/publish?source=official'],
    ['https://creator.xiaohongshu.com/publish/publish?source=official']
  ])
})

it('leaves automated clicks, unrelated links and other origins untouched, especially the final publish button', () => {
  const f = fixture()
  expect(f.click('<button class="publish-btn"><span>＋</span></button>', false).preventDefault).not.toHaveBeenCalled()
  f.click('<a href="https://example.com"><span>发布</span></a>')
  f.click('<button><span>＋</span></button>')
  expect(f.navigate).not.toHaveBeenCalled()

  for (const url of ['https://creator.xiaohongshu.com/publish/publish', 'https://www.zhihu.com/', 'https://www.xiaohongshu.com.evil.test/']) {
    const other = fixture(url)
    other.click('<button class="publish-btn"><span>发布</span></button>')
    expect(other.navigate).not.toHaveBeenCalled()
  }
})
