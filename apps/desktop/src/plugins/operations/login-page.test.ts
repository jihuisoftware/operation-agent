import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { inspectLoginPage, loginPlatform } from './login-page'

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(100)
})
afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

function page(hostname: string, html: string) {
  vi.stubGlobal('location', { hostname, protocol: 'https:', href: `https://${hostname}/` })
  document.body.innerHTML = html
}

it('requires an account entry in navigation, never a public note author or text mentioning login', () => {
  page(
    'www.xiaohongshu.com',
    '<article><a href="https://www.xiaohongshu.com/user/profile/author">我</a><p>登录教程</p></article>'
  )
  expect(inspectLoginPage('xiaohongshu').state).toBe('unknown')
  document.body.innerHTML += '<nav><a href="https://www.xiaohongshu.com/user/profile/mine">我</a></nav>'
  expect(inspectLoginPage('xiaohongshu')).toEqual({ state: 'logged_in', account_id: 'mine' })
  document.body.innerHTML += '<div role="dialog">请进行安全验证</div>'
  expect(inspectLoginPage('xiaohongshu').state).toBe('verification')
  page('www.xiaohongshu.com', '<nav><button>登录</button></nav>')
  expect(inspectLoginPage('xiaohongshu').state).toBe('logged_out')
})

it.each([
  [
    'zhihu',
    'www.zhihu.com',
    '<div class="AppHeader-userInfo"><a href="https://www.zhihu.com/people/mine">账号</a></div>',
    'mine'
  ],
  [
    'bilibili',
    'www.bilibili.com',
    '<div class="bili-header__bar"><div class="header-avatar-wrap"><a href="https://space.bilibili.com/123">头像</a></div></div>',
    '123'
  ],
  ['douyin', 'www.douyin.com', '<nav><a href="https://www.douyin.com/user/mine">我</a></nav>', 'mine'],
  [
    'wechat',
    'mp.weixin.qq.com',
    '<div class="weui-desktop-account"><span class="weui-desktop-account__nickname">账号</span><a>退出</a></div>',
    ''
  ]
])('reads an explicit %s account signal without taking cookies or query tokens', (platform, host, html, account) => {
  page(host, html)
  expect(inspectLoginPage(platform)).toEqual({ state: 'logged_in', account_id: account })
})

it('rejects lookalike hosts, ambiguous accounts and public WeChat articles', () => {
  expect(loginPlatform('https://www.xiaohongshu.com.evil.test')).toBeNull()
  expect(loginPlatform('http://www.zhihu.com')).toBeNull()
  page('mp.weixin.qq.com', '<article>欢迎关注，账号登录教程</article>')
  expect(inspectLoginPage('wechat').state).toBe('unknown')
  page(
    'www.xiaohongshu.com',
    '<nav><a href="https://www.xiaohongshu.com/user/profile/a">我</a><a href="https://www.xiaohongshu.com/user/profile/b">我</a></nav>'
  )
  expect(inspectLoginPage('xiaohongshu').state).toBe('unknown')
  page('www.xiaohongshu.com.evil.test', document.body.innerHTML)
  expect(inspectLoginPage('xiaohongshu').state).toBe('unknown')
})

it('recognizes the channel-list account entry after QR login, including a sibling label', () => {
  page(
    'www.xiaohongshu.com',
    '<ul class="channel-list"><li class="user side-bar-component"><a aria-label="头像" href="https://www.xiaohongshu.com/user/profile/mine"><img alt="头像"></a><span>我</span></li></ul>'
  )
  expect(inspectLoginPage('xiaohongshu')).toEqual({ state: 'logged_in', account_id: 'mine' })
})

it('recognizes a labelled icon-only navigation entry with a relative account link', () => {
  page(
    'www.xiaohongshu.com',
    '<nav><a title="个人中心" href="/user/profile/mine"><svg></svg></a></nav>'
  )
  expect(inspectLoginPage('xiaohongshu')).toEqual({ state: 'logged_in', account_id: 'mine' })
})

it('can execute the serialized probe in a guest without access to module helpers', () => {
  page('www.xiaohongshu.com', '<nav><a href="https://www.xiaohongshu.com/user/profile/mine">我</a></nav>')
  const probe = new Function(`return (${inspectLoginPage.toString()})`)()
  expect(probe('xiaohongshu')).toEqual({ state: 'logged_in', account_id: 'mine' })
})
