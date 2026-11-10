/** Runs inside the guest; keep this function self-contained for executeJavaScript. */
export function installPublishEntry(
  page: Document = document,
  pageUrl: string = location.href,
  navigate: (url: string) => void = url => location.assign(url)
) {
  if (new URL(pageUrl).origin !== 'https://www.xiaohongshu.com') { return }
  const root = page as Document & { __operationsPublishEntry?: boolean }

  if (root.__operationsPublishEntry) { return }
  root.__operationsPublishEntry = true

  page.addEventListener('click', event => {
    // Only a person's primary click changes navigation; automated tool clicks keep their contract.
    if (!event.isTrusted || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) { return }
    const target = event.target as Element | null

    if (!target?.closest) { return }
    const publishButton = target.closest('.publish-btn')
    const anchor = target.closest<HTMLAnchorElement>('a[href]')
    const url = anchor ? new URL(anchor.href, pageUrl) : null
    const publishLink = url?.origin === 'https://creator.xiaohongshu.com' && url.pathname === '/publish/publish'

    if (!publishButton && !publishLink) { return }
    event.preventDefault()
    event.stopImmediatePropagation()
    // Stay in the account's existing guest/partition; never open an OS browser or submit a post.
    navigate('https://creator.xiaohongshu.com/publish/publish?source=official')
  }, true)
}
