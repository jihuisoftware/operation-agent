/** Shared read-only inventory/readiness logic inside the isolated platform page. */
export function xhsInteractionDom(kind: string) {
  const text = (element: Element) => (element.textContent || '').trim()

  const visible = (element: Element) => {
    const rect = element.getBoundingClientRect()

    return !element.closest('[hidden],[aria-hidden="true"]') && rect.bottom >= 0 && rect.right >= 0 && Boolean((element as HTMLElement).offsetWidth || element.getClientRects().length)
  }

  const all = (selector: string, root: ParentNode = document) => Array.from(root.querySelectorAll<HTMLElement>(selector)).filter(visible)

  const profileId = (element: Element) => {
    const link = element.matches('a[href]') ? element as HTMLAnchorElement : element.querySelector<HTMLAnchorElement>('a[href*="/user/profile/"]')

    return link && new URL(link.href).origin === location.origin ? new URL(link.href).pathname.match(/^\/user\/profile\/([^/]+)\/?$/)?.[1] : undefined
  }

  const noteLink = (element: Element) => Array.from(element.querySelectorAll<HTMLAnchorElement>('a[href*="/explore/"],a[href*="/search_result/"]'))
    .filter(link => new URL(link.href).origin === location.origin && /\/(explore|search_result)\/[^/]+/.test(new URL(link.href).pathname))
    .sort((a, b) => Number(new URL(b.href).searchParams.has('xsec_token')) - Number(new URL(a.href).searchParams.has('xsec_token')))[0]

  const selectors: Record<string, string> = { comment: 'section.note-item', reply: '[data-comment-id],.comment-item', dm: '[data-message-id]', follow: '[data-user-id],.user-item' }
  const rows = all(selectors[kind] || '[data-operation-item]')

  if (kind === 'follow') {
    for (const link of all('a[href*="/user/profile/"]')) {
      let row: HTMLElement | null = link.parentElement

      while (row && row !== document.body) {
        const identities = new Set(all('a[href*="/user/profile/"]', row).map(profileId).filter(Boolean))
        const relation = all('button,[role="button"],a,span', row).some(element => /^(回关|互相关注|已关注)$/.test(text(element)))

        if (identities.size === 1 && relation) { rows.push(row);

 break }

        if (identities.size > 1) { break }
        row = row.parentElement
      }
    }
  }

  const identifier = (element: HTMLElement) => {
    const link = noteLink(element)

    const ids: Record<string, string | undefined> = {
      comment: link ? `note:${new URL(link.href).pathname.split('/').filter(Boolean).at(-1)}` : undefined,
      reply: element.dataset.commentId,
      dm: element.dataset.messageId,
      follow: element.dataset.userId || profileId(element)
    }

    return ids[kind]
  }

  const unique = new Map<string, HTMLElement>()

  for (const row of rows) {
    const id = identifier(row)

    if (id && !unique.has(id)) { unique.set(id, row) }
  }

  const body = document.body?.innerText || document.body?.textContent || ''

  const emptyPatterns: Record<string, RegExp> = {
    comment: /暂无.*结果|没有.*结果|未找到.*结果/,
    reply: /暂无.*(评论|通知)|没有.*(评论|通知)|还没有收到.*(评论|通知)/,
    dm: /暂无.*(消息|私信|聊天)|没有.*(消息|私信|聊天)|还没有收到.*(消息|私信)/,
    follow: /暂无.*粉丝|没有.*粉丝|还没有.*粉丝/
  }

  const unavailable = /登录状态异常|你访问的页面不见了|笔记不存在|内容无法展示|内容已删除/.test(body)
  const matchesNote = (target: string) => target.startsWith('note:') && location.pathname.split('/').filter(Boolean).at(-1) === target.slice(5)
  const followsMe = (root: Element) => /关注了你|已关注你/.test(text(root)) || all('button,[role="button"],a,span', root).some(element => /^互相关注$/.test(text(element)))
  const alreadyFollowing = (root: Element) => all('button,[role="button"],a,span', root).some(element => /^(互相关注|已关注)$/.test(text(element)))

  return { rows: [...unique.values()], identifier, noteLink, followsMe, alreadyFollowing, matchesNote, unavailable,
    empty: emptyPatterns[kind]?.test(body) === true, blank: !body.trim() }
}
