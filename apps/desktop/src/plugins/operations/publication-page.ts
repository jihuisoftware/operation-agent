/** Publication evidence and a fixed read-only list filter; never a publish or edit control. */
export function publicationPage(request: { operation: string; payload: Record<string, any> }) {
  const { operation, payload } = request
  const text = (e: Element | null) => (e?.textContent || '').trim()
  const normalize = (s: string) => s.replace(/\s+/g, '')

  const noteId = (url: URL) => {
    if (url.protocol !== 'https:' || url.hostname !== 'www.xiaohongshu.com') { return '' }

    return url.pathname.match(/^\/explore\/([^/]+)$/)?.[1] || url.pathname.match(/^\/user\/profile\/[^/]+\/([^/]+)$/)?.[1] || ''
  }

  if (!document.body) { return { ready: false } }

  if (/安全验证|拖动滑块/.test(document.body.innerText || '')) { throw new Error('页面要求人工安全验证') }

  const notesPage = () => {
    if (location.pathname !== `/user/profile/${payload.account_id}`) { throw new Error('笔记列表账号不匹配') }
    const cards = Array.from(document.querySelectorAll('section.note-item'))

    const notes = cards.flatMap(card => {
      const links = Array.from(card.querySelectorAll<HTMLAnchorElement>('a[href]')).filter(a => noteId(new URL(a.href)))
      const link = links.find(a => text(a)) || links[0]

      if (!link) { return [] }

      return [{ id: noteId(new URL(link.href)), url: link.href, title: text(card.querySelector('.title')) || text(link) }]
    })

    const empty = /还没有发布过笔记|还没有发布笔记|暂无笔记/.test(document.body.innerText || '')

    return { ready: notes.length > 0 || empty, notes }
  }

  const inspectPage = () => {
    const id = noteId(new URL(location.href))

    if (!id) { return { ready: false } }
    const description = document.querySelector('#detail-desc,.note-detail .desc')

    if (!description) { return { ready: false } }
    const authors = Array.from(document.querySelectorAll<HTMLAnchorElement>('.author a[href*="/user/profile/"],a.username[href*="/user/profile/"]'))

    if (!authors.length) { return { ready: false } }

    const checks = {
      author: authors.some(a => new URL(a.href).pathname === `/user/profile/${payload.account_id}`),
      title: text(document.querySelector('#detail-title,.note-detail .title')) === payload.content.title,
      body: normalize((description as HTMLElement).innerText || text(description)) === normalize(payload.content.body)
    }

    const images = Array.from(document.querySelectorAll<HTMLImageElement>('.swiper-slide img,img.note-slider-img'))
      .map(e => e.currentSrc || e.src).filter(url => url.startsWith('https://'))

    return { ready: true, id, url: location.href, checks, actual: { title: text(document.querySelector('#detail-title,.note-detail .title')), body: (description as HTMLElement).innerText || text(description) }, images: [...new Set(images)], platform: 'unknown' }
  }

  const imageKey = (value: string) => {
    try {
      const url = new URL(value)
      if (url.protocol !== 'https:' || !url.hostname.endsWith('.xhscdn.com')) { return '' }
      return url.pathname.split('!')[0].split('/').at(-1) || ''
    } catch { return '' }
  }
  const identifiesCard = (card: Element) => {
    const ids = [card.getAttribute('data-note-id'), card.getAttribute('data-noteid'),
      ...Array.from(card.querySelectorAll<HTMLAnchorElement>('a[href]')).map(a => noteId(new URL(a.href)))].filter(Boolean)
    // An explicit different ID beats a coincidentally identical title/cover.
    if (ids.length) { return ids.every(id => id === payload.note_id) }
    const keys = (payload.images || []).map(imageKey).filter(Boolean)
    return text(card.querySelector('.note-card__title,.note-title,.title')) === payload.content.title &&
      Array.from(card.querySelectorAll<HTMLImageElement>('img')).some(img => keys.includes(imageKey(img.currentSrc || img.src)))
  }
  const statusLabel = (value: string) => {
    const normalized = value.replace(/\s+/g, '').replace(/[（(]\d+[）)]$/, '')
    const statuses: Record<string, string> = { '审核中': 'reviewing', '审核未通过': 'rejected', '审核不通过': 'rejected', '未通过': 'rejected', '已发布': 'published' }
    return statuses[normalized]
  }
  const cardStatuses = (card: Element) => [card, ...Array.from(card.querySelectorAll('*'))]
    .filter(e => !e.closest('.note-card__title,.note-title,.title,.desc,.note-desc'))
    .flatMap(e => Array.from(e.childNodes).filter(n => n.nodeType === 3).map(n => (n.textContent || '').trim()))
    .filter(label => label !== payload.content.title && label !== payload.content.body)
    .map(statusLabel).filter(Boolean)

  const visible = (element: Element) => {
    for (let node: Element | null = element; node; node = node.parentElement) {
      if (node.hasAttribute('hidden') || node.getAttribute('aria-hidden') === 'true') { return false }
      const style = getComputedStyle(node)
      if (style.display === 'none' || style.visibility === 'hidden') { return false }
    }
    return true
  }

  const tabEvidence = () => Array.from(document.querySelectorAll('div,span,button,a,[role="tab"]'))
    .filter(e => visible(e) && !e.closest('.note-card,[data-note-id],[data-noteid]') && Boolean(statusLabel(text(e))))
    .slice(0, 12).map(e => ({ tag: e.tagName, class: String(e.className).slice(0, 160),
      selected: e.getAttribute('aria-selected'), label: text(e).slice(0, 30) }))

  const managerPage = () => {
    if (location.hostname !== 'creator.xiaohongshu.com' || !location.pathname.includes('/note-manager')) {
      return { ready: false, platform: 'unknown', reason: '不在笔记管理页' }
    }
    const all = Array.from(document.querySelectorAll('.note-card,[data-note-id],[data-noteid]')).filter(visible)
    // Nested ID wrappers are one card, not multiple publications.
    const cards = all.filter(card => !all.some(parent => parent !== card && parent.contains(card))).filter(identifiesCard)
    const evidence = { cards: all.length, matched: cards.length, tabs: tabEvidence() }
    if (cards.length !== 1) { return { ready: all.length > 0, platform: 'unknown', evidence, reason: '未唯一匹配目标笔记' } }
    const found = [...new Set(cardStatuses(cards[0]))]
    if (found.length) {
      return { ready: true, platform: found.length === 1 ? found[0] : 'unknown', evidence, status_source: 'card' }
    }
    // Only an explicitly selected platform tab is evidence; an inactive tab or title is not.
    const selected = Array.from(document.querySelectorAll('[role="tab"][aria-selected="true"],.tabs .active,.tab.active,.tab-item.active,.tab-item--active'))
      .filter(tab => visible(tab) && !tab.closest('.note-card,[data-note-id],[data-noteid]'))
      .map(tab => statusLabel(text(tab))).filter(Boolean)
    const statuses = [...new Set(selected)]
    return { ready: true, platform: statuses.length === 1 ? statuses[0] : 'unknown', evidence,
      status_source: statuses.length === 1 ? 'selected_tab' : 'unavailable' }
  }

  const selectPublished = () => {
    if (location.hostname !== 'creator.xiaohongshu.com' || !location.pathname.includes('/note-manager')) {
      return { selected: false }
    }
    const candidates = Array.from(document.querySelectorAll<HTMLElement>('[role="tab"],.tab-item,.tab,.tabs > *'))
      .filter(e => visible(e) && !e.closest('.note-card,[data-note-id],[data-noteid]') && statusLabel(text(e)) === 'published')
    const leaves = candidates.filter(e => !candidates.some(other => e !== other && e.contains(other)))
    if (leaves.length !== 1) { return { selected: false, candidates: leaves.length } }
    leaves[0].click()
    return { selected: true }
  }

  const readers: Record<string, () => object> = { notes: notesPage, inspect: inspectPage, manager: managerPage, manager_select_published: selectPublished }

  if (!readers[operation]) { throw new Error('不支持的发布核对步骤') }

  return readers[operation]()
}
