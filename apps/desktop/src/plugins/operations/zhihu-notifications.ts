import type { BrowserExecution } from './browser-execution'
import { navigateGuest } from './browser-navigation'
import { READINESS_MS, SCRIPT_MS } from './browser-timeouts'
import { waitForRead } from './browser-wait'
import type { Api, BrowserCommand, Guest, OperationsState } from './types'

export const zhihuSources = { follow: '关注我的', reaction: '赞同与喜欢', reply: '评论与回复' }

export function zhihuAccount(open: boolean) {
  if (location.origin !== 'https://www.zhihu.com' || location.pathname !== '/notifications') {
    throw new Error('请在账号页登录知乎，并完成网页验证')
  }
  const link = [...document.querySelectorAll<HTMLAnchorElement>('header a[href*="/people/"], .Menu a[href*="/people/"], [role="menu"] a[href*="/people/"]')].find(a =>
    ['我的主页', '个人主页'].includes(a.textContent?.trim() || '') && a.getClientRects().length)
  if (link && new URL(link.href).origin === location.origin) {
    return new URL(link.href).pathname.match(/^\/people\/([^/]+)\/?$/)?.[1] || ''
  }
  const button = document.querySelector<HTMLElement>('header button.AppHeader-profileEntry')
  if (open && button && button.getAttribute('aria-expanded') !== 'true') { button.click() }

  return ''
}

export function zhihuTab(label: string, select: boolean) {
  if (location.origin !== 'https://www.zhihu.com' || location.pathname !== '/notifications') {
    throw new Error('知乎通知页面已离开，请检查登录状态')
  }
  const norm = (node?: Element | null) => (node?.textContent || '').replace(/[\s\u200b]/g, '')
  const section = document.querySelector('.Notifications-Section')
  const toggle = section?.querySelector<HTMLElement>('.Notifications-EntryMenu button')
  if (!toggle) { return false }
  if (norm(toggle) === label) { return true }
  if (!select) { return false }
  const choices = [...document.querySelectorAll<HTMLElement>('button.Notifications-MenuItem')].filter(b => b.getClientRects().length)
  const match = choices.filter(b => norm(b) === label)
  if (match.length === 1) { match[0].click() } else if (!choices.length) { toggle.click() }

  return false
}

export function zhihuRows() {
  const section = document.querySelector('.Notifications-Section')
  if (location.origin !== 'https://www.zhihu.com' || location.pathname !== '/notifications' || !section) { return null }
  const rows = [...section.querySelectorAll<HTMLElement>('.NotificationList-Item')]
  if (!rows.length) {
    return section.querySelector('.NotificationList-EmptyState')?.textContent?.includes('没有收到此类通知') ? [] : null
  }
  const items = []
  for (const row of rows) {
    const clock = row.querySelector('time,.NotificationList-ItemTime,.NotificationItem-time,.NotificationItem-Time,.NotificationList-ItemMeta [title]')
    const time = clock?.textContent?.trim() || ''
    const text = (row.innerText || row.textContent || '').trim()
    const urls = [...row.querySelectorAll<HTMLAnchorElement>('a[href]')].map(a => new URL(a.getAttribute('href')!, location.href))
      .filter(u => u.origin === location.origin).map(u => u.pathname)
    const id = row.dataset.notificationId || row.dataset.id
    if (!text || (!urls.length && !id)) { return null }
    items.push({ id: id || JSON.stringify([urls, time ? text.replace(time, '').trim() : text]),
      text: text.slice(0, 2000), time_label: time, time_absolute: clock?.getAttribute('datetime') || clock?.getAttribute('title') })
  }

  return items.length ? items : null
}

export async function receiveZhihu(command: BrowserCommand, guest: Guest, api: Api, context: BrowserExecution, sleep: (ms: number) => Promise<unknown>) {
  const check = async () => {
    context.assert()
    const state = await api<OperationsState>('/policy')
    if (!state.policy.enabled || state.policy.paused || state.web_held || state.version !== command.payload.policy_version) {
      throw new Error('知乎收件已暂停或规则已变化')
    }
  }
  const run = (script: string) => context.wait(() => guest.executeJavaScript(script), SCRIPT_MS, true, '读取知乎通知')
  const wait = <T,>(read: () => Promise<T>, ready: (result: T) => boolean) => waitForRead(read, ready, READINESS_MS, false, sleep, context)
  await check()
  await navigateGuest(guest, 'https://www.zhihu.com/notifications', sleep, context, true)
  const identity = async () => {
    return wait<string>(() => run(`(${zhihuAccount.toString()})(true)`), Boolean)
  }
  const account = await identity()
  const groups: Record<string, unknown[]> = {}
  for (const [source, label] of Object.entries(zhihuSources)) {
    await check()
    const tab = (select: boolean) => run(`(${zhihuTab.toString()})(${JSON.stringify(label)},${select})`)
    await wait(() => tab(true), Boolean)
    groups[source] = await wait(async () => await tab(false) ? run(`(${zhihuRows.toString()})()`) : null, Array.isArray)
  }
  if (await identity() !== account) { throw new Error('知乎登录账号已变化，请重新接收') }

  return { notification_platform: 'zhihu', platform_identity: account, groups }
}
