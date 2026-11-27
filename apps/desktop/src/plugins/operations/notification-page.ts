// Runs inside the signed-in notification page. Read only the selected tab's loaded rows.
export function notificationPage(source: string, select: boolean, readRow = readNotificationRow) {
  const titles: Record<string, string> = { reply: '评论和@', reaction: '赞和收藏', follow: '新增关注' }
  if (location.origin !== 'https://www.xiaohongshu.com' || location.pathname !== '/notification' || !titles[source]) {
    throw new Error('通知页地址或来源不匹配')
  }
  const tabs = [...document.querySelectorAll<HTMLElement>('.reds-tabs-list .reds-tab-item')].filter(tab =>
    [...tab.querySelectorAll('span')].some(label => label.textContent?.replace(/\s/g, '') === titles[source]))
  const tab = tabs.length === 1 ? tabs[0] : null

  if (!tab) { return { ready: false, items: [] } }
  if (select) {
    if (!tab.classList.contains('active')) { tab.click() }

    return { ready: true, items: [] }
  }

  const panel = document.querySelector('.tabs-content-container')
  if (!tab.classList.contains('active') || !panel || panel.querySelector('.loading-container')) {
    return { ready: false, items: [] }
  }
  const rows = [...panel.querySelectorAll<HTMLElement>('.container')]
  const items = rows.map(row => readRow(row, source)).filter(item => item !== null)
  const empty = !rows.length && /^(暂无|还没有|没有收到|暂时没有)/.test(panel.textContent?.trim() || '')

  return { ready: items.length > 0 || empty, items }
}

export function readNotificationRow(row: HTMLElement, source: string) {
  const sender = row.querySelector<HTMLAnchorElement>('.user-info a[href*="/user/profile/"]')
  const hint = row.querySelector('.interaction-hint span:not(.interaction-time)')?.textContent?.trim() || ''
  const content = row.querySelector('.interaction-content')?.textContent?.trim() || ''
  const actor = sender && new URL(sender.getAttribute('href')!, location.href)
  if (!actor || actor.origin !== location.origin || !hint) { return null }
  // Ignore old rows while the platform switches tabs. Relative times and signed URLs are unstable IDs.
  const rowSource = /^(?:赞|点赞|收藏)/.test(hint) ? 'reaction' : /^(?:开始关注|关注了你)/.test(hint) ? 'follow' :
    /评论|回复|提及|@/.test(hint) ? 'reply' : ''
  if (rowSource !== source) { return null }
  const user = actor.pathname.match(/^\/user\/profile\/([^/]+)\/?$/)?.[1]
  if (!user) { return null }
  const note = row.getAttribute('note-id') || ''
  const quote = row.querySelector('.quote-info')?.textContent?.trim() || ''
  const id = source === 'follow' ? user : row.dataset.commentId || row.dataset.notificationId ||
    JSON.stringify([user, note, hint, content, quote])
  const time = row.querySelector('.interaction-time')
  return { id, time_label: time?.textContent?.trim(), time_absolute: time?.getAttribute('datetime') || time?.getAttribute('title'),
    text: [sender?.textContent?.trim(), hint, content, quote].filter(Boolean).join(' · ').slice(0, 2000),
    url: actor.origin + actor.pathname, follows_me: source === 'follow',
    already_following: source === 'follow' && /^(互相关注|已关注)$/.test(row.querySelector('.follow-button')?.textContent?.trim() || '') }
}
