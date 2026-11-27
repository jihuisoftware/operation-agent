import { afterEach, expect, it, vi } from 'vitest'
import { zhihuRows, zhihuSources, zhihuTab } from './zhihu-notifications'

afterEach(() => { document.body.innerHTML = ''; vi.unstubAllGlobals() })

it.each([['follow', '关注我的'], ['reaction', '赞同与喜欢'], ['reply', '评论与回复']] as const)(
  'reads the loaded Zhihu category %s and preserves its platform time', (source, label) => {
    vi.stubGlobal('location', new URL('https://www.zhihu.com/notifications'))
    document.body.innerHTML = '<main class="Notifications-Section"><div class="Notifications-EntryMenu"><button></button></div><div class="NotificationList-Item"></div></main>'
    document.querySelector('button')!.textContent = label + '\u200b'
    expect(zhihuTab(zhihuSources[source], false)).toBe(true)
    expect(zhihuRows()).toBeNull()
    document.querySelector('.NotificationList-Item')!.innerHTML = '<a href="/people/u">用户</a>通知<time datetime="2026-11-27T10:00:00+08:00">昨天</time>'
    const row = zhihuRows()![0]
    expect(row).toMatchObject({ time_label: '昨天', time_absolute: '2026-11-27T10:00:00+08:00' })
    document.querySelector('time')!.textContent = '前天'
    expect(zhihuRows()![0].id).toBe(row.id)
  })
