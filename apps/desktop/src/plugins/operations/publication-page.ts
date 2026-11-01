/** Read-only DOM evidence. Serialized into the guest; no model-generated selectors or actions. */
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

  const managerPage = () => {
    if (!document.querySelector('.note-card') && !/暂无笔记/.test(document.body.innerText)) { return { ready: false } }
    const imageKey = (url: string) => new URL(url).pathname.split('/').at(-1)

    const cards = Array.from(document.querySelectorAll('.note-card')).filter(card =>
      card.getAttribute('data-note-id') === payload.note_id ||
      Array.from(card.querySelectorAll<HTMLAnchorElement>('a[href]')).some(a => noteId(new URL(a.href)) === payload.note_id) ||
      (text(card.querySelector('.note-card__title')) === payload.content.title &&
       Array.from(card.querySelectorAll<HTMLImageElement>('img')).some(img => (payload.images || []).some((url: string) => imageKey(url) === imageKey(img.src)))))

    // Cards without a stable note ID cannot be joined to an action by title alone.
    if (cards.length !== 1) { return { ready: true, platform: 'unknown' } }
    const statuses: Record<string, string> = { '审核中': 'reviewing', '审核未通过': 'rejected', '审核不通过': 'rejected', '未通过': 'rejected', '已发布': 'published' }

    // User-authored titles/descriptions are not evidence of platform review status.
    const labels = [cards[0], ...Array.from(cards[0].querySelectorAll('*'))]
      .filter(e => !e.closest('.note-card__title,.title,.desc'))
      .flatMap(e => Array.from(e.childNodes).filter(n => n.nodeType === 3).map(n => (n.textContent || '').trim()))

    const found = [...new Set(labels.map(label => statuses[label]).filter(Boolean))]

    return { ready: true, platform: found.length === 1 ? found[0] : 'unknown' }
  }

  const readers: Record<string, () => object> = { notes: notesPage, inspect: inspectPage, manager: managerPage }

  if (!readers[operation]) { throw new Error('不支持的发布核对步骤') }

  return readers[operation]()
}
