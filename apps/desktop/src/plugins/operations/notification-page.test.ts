import { afterEach, expect, it, vi } from 'vitest'

import { notificationPage } from './notification-page'

afterEach(() => { document.body.innerHTML = ''; vi.unstubAllGlobals() })

it('waits through loading and ignores stale likes on the comments tab', () => {
  vi.stubGlobal('location', new URL('https://www.xiaohongshu.com/notification'))
  document.body.innerHTML = '<nav class="reds-tabs-list"><div class="reds-tab-item active"><span>评论和 @</span></div></nav><div class="tabs-content-container"><div class="loading-container"></div></div>'
  expect(notificationPage('reply', false).ready).toBe(false)
  const panel = document.querySelector('.tabs-content-container')!
  panel.innerHTML = '<div class="container" note-id="n"><div class="user-info"><a href="/user/profile/u">昵称</a></div><div class="interaction-hint"><span>赞了你的评论</span><span class="interaction-time">昨天</span></div></div>'
  expect(notificationPage('reply', false)).toEqual({ ready: false, items: [] })
  panel.querySelector('.interaction-hint span')!.textContent = '回复了你的评论'
  const first = notificationPage('reply', false)
  panel.querySelector('.interaction-time')!.textContent = '前天'
  expect(first.ready).toBe(true)
  expect(notificationPage('reply', false).items[0].id).toEqual(first.items[0].id)
})

it('reads the platform time separately from the identity and prefers a precise timestamp', () => {
  vi.stubGlobal('location', new URL('https://www.xiaohongshu.com/notification'))
  document.body.innerHTML = '<nav class="reds-tabs-list"><div class="reds-tab-item active"><span>新增关注</span></div></nav><div class="tabs-content-container"><div class="container"><div class="user-info"><a href="/user/profile/u">用户</a></div><div class="interaction-hint"><span>开始关注你了</span><time class="interaction-time" datetime="2025-05-13T10:15:02+08:00">昨天</time></div></div></div>'
  expect(notificationPage('follow', false).items[0]).toMatchObject({ id: 'u', time_label: '昨天', time_absolute: '2025-05-13T10:15:02+08:00' })
})
