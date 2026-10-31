/** Pure read-only DOM inspection, serialized into the isolated guest. No cookies or credentials leave it. */
export function inspectLoginPage(platform: string) {
  const visible = (e: Element) =>
    Boolean((e as HTMLElement).offsetWidth || (e as HTMLElement).offsetHeight || e.getClientRects().length)

  const all = (selector: string) => Array.from(document.querySelectorAll<HTMLElement>(selector)).filter(visible)
  const text = (e: Element) => (e.textContent || '').trim()

  const hosts: Record<string, string[]> = {
    xiaohongshu: ['www.xiaohongshu.com', 'creator.xiaohongshu.com'],
    zhihu: ['www.zhihu.com'],
    bilibili: ['www.bilibili.com', 'passport.bilibili.com'],
    wechat: ['mp.weixin.qq.com'],
    douyin: ['www.douyin.com']
  }

  const result = (state: 'logged_in' | 'logged_out' | 'verification' | 'unknown', account_id = '') => ({
    state,
    account_id
  })

  if (location.protocol !== 'https:' || !hosts[platform]?.includes(location.hostname)) {
    return result('unknown')
  }

  const challenge = all('[class*="captcha"],[class*="verify"],[role="dialog"]').some(e =>
    /请.*验证|安全验证|安全检查|拖动滑块|验证码验证/.test(text(e))
  )

  if (challenge) {
    return result('verification')
  }

  const login = all(
    '[class*="login-container"],[class*="login-panel"],[class*="Login"],[class*="SignFlow"],.login__type__container,[role="dialog"]'
  ).some(e => /扫码登录|手机登录|密码登录|登录后|登录注册|账号登录/.test(text(e)))

  if (login) {
    return result('logged_out')
  }

  const selectors: Record<string, string> = {
    xiaohongshu:
      'nav a[href*="/user/profile/"],aside a[href*="/user/profile/"],[role="navigation"] a[href*="/user/profile/"],.side-bar a[href*="/user/profile/"],.channel-list a[href*="/user/profile/"],.user.side-bar-component a[href*="/user/profile/"],a.user.side-bar-component[href*="/user/profile/"]',
    zhihu: '.AppHeader-userInfo a[href*="/people/"],.AppHeader-profile a[href*="/people/"]',
    bilibili:
      '.bili-header__bar .header-avatar-wrap a[href*="space.bilibili.com/"],.bili-header__bar a.header-entry-mini[href*="space.bilibili.com/"]',
    douyin: 'header a[href*="/user/"],nav a[href*="/user/"], [data-e2e="navigation-my"] a[href*="/user/"]'
  }

  const paths: Record<string, RegExp> = {
    xiaohongshu: /^\/user\/profile\/([^/]+)\/?$/,
    zhihu: /^\/people\/([^/]+)\/?$/,
    bilibili: /^\/(\d+)\/?$/,
    douyin: /^\/user\/([^/]+)\/?$/
  }

  const accountHosts: Record<string, string> = {
    xiaohongshu: 'www.xiaohongshu.com',
    zhihu: 'www.zhihu.com',
    bilibili: 'space.bilibili.com',
    douyin: 'www.douyin.com'
  }

  const links = selectors[platform] ? all(selectors[platform]) : []

  const ids = new Set(
    links.flatMap(e => {
      const labels = [
        text(e),
        e.getAttribute('aria-label') || '',
        text(e.closest('.side-bar-component,.channel-list li') || e)
      ]

      if (
        ['xiaohongshu', 'douyin'].includes(platform) &&
        !labels.some(label => /^(我|我的|我的主页|个人主页)$/.test(label.replace(/\s+/g, '')))
      ) {
        return []
      }

      const url = new URL((e as HTMLAnchorElement).href, location.href)

      const id =
        url.protocol === 'https:' && url.hostname === accountHosts[platform]
          ? url.pathname.match(paths[platform])?.[1]
          : ''

      return id ? [id] : []
    })
  )

  if (ids.size === 1) {
    return result('logged_in', [...ids][0])
  }

  if (ids.size > 1) {
    return result('unknown')
  }

  // The public article reader is not the official-account console. Never inspect query tokens.
  if (platform === 'wechat') {
    const account = all('.weui-desktop-account__nickname,.account_nickname')
    const logout = all('.weui-desktop-account a,.account a').some(e => /^(退出|退出登录)$/.test(text(e)))

    if (account.length === 1 && logout) {
      return result('logged_in')
    }
  }

  const loginButtons = all(
    'header button,header a,nav button,nav a,.side-bar button,.login__type__container button,.login__type__container a'
  )

  if (loginButtons.some(e => /^(登录|登录\/注册|登录注册|立即登录)$/.test(text(e)))) {
    return result('logged_out')
  }

  return result('unknown')
}

export function loginPlatform(url: string): string | null {
  try {
    const parsed = new URL(url)

    if (parsed.protocol !== 'https:') {
      return null
    }

    const hosts: Record<string, string> = {
      'www.xiaohongshu.com': 'xiaohongshu',
      'creator.xiaohongshu.com': 'xiaohongshu',
      'www.zhihu.com': 'zhihu',
      'www.bilibili.com': 'bilibili',
      'passport.bilibili.com': 'bilibili',
      'mp.weixin.qq.com': 'wechat',
      'www.douyin.com': 'douyin'
    }

    return hosts[parsed.hostname] || null
  } catch {
    return null
  }
}
