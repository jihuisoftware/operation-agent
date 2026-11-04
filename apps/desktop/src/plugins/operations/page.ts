import { xhsInteractionDom } from './interaction-dom'
import { xhsPublishControl } from './publish-control'

/** Runs in the isolated guest. Unknown DOM shapes fail closed and return evidence, never success. */
export function xhsPage(command: { operation: string; payload: Record<string, any> }, publishControl = xhsPublishControl, interactionDom = xhsInteractionDom) {
  const { operation, payload } = command

  const visible = (element: Element) => {
    if (element.closest('[aria-hidden="true"],[hidden]')) { return false }
    const rect = element.getBoundingClientRect()

    return rect.bottom >= 0 && rect.right >= 0 && Boolean(
      (element as HTMLElement).offsetWidth || (element as HTMLElement).offsetHeight || element.getClientRects().length
    )
  }

  const all = (selector: string, root: ParentNode = document) =>
    Array.from(root.querySelectorAll<HTMLElement>(selector)).filter(visible)

  const text = (element: Element) => (element.textContent || '').trim()

  const unique = (items: HTMLElement[], label: string) => {
    if (items.length !== 1) {
      throw new Error(`${label}匹配到 ${items.length} 个元素，等待人工处理`)
    }

    return items[0]
  }

  const button = (label: string, root: ParentNode = document) =>
    unique(
      all('button,[role="button"],a,span', root).filter(
        e => text(e) === label && !all('button,[role="button"],a,span', e).some(child => text(child) === label)
      ),
      label
    )

  const blocked = all('[class*="captcha"],[class*="verify"],[class*="login-container"]').some(e =>
    text(e).match(/验证|登录|安全检查/)
  )

  if (blocked) {
    throw new Error('页面要求登录或验证，请人工接管')
  }

  const setText = (element: HTMLElement, value: string) => {
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
      const prototype = element instanceof HTMLInputElement ? HTMLInputElement.prototype : HTMLTextAreaElement.prototype
      Object.getOwnPropertyDescriptor(prototype, 'value')!.set!.call(element, value)
    } else {
      element.replaceChildren(...value.split('\n').map(line => {
        const paragraph = document.createElement('p')
        paragraph.textContent = line

        return paragraph
      }))
    }

    element.dispatchEvent(new Event('input', { bubbles: true }))
    element.dispatchEvent(new Event('change', { bubbles: true }))
  }

  const inventory = () => interactionDom(payload.kind)
  const items = () => inventory().rows
  const identifier = (element: HTMLElement) => inventory().identifier(element)
  const noteLink = (element: HTMLElement) => inventory().noteLink(element)

  const findItem = () =>
    unique(
      items().filter(e => identifier(e) === payload.target),
      '互动对象'
    )

  const validatePost = () => {
    const title = unique(all('input[placeholder*="标题"],textarea[placeholder*="标题"]'), '标题') as HTMLInputElement
    const body = unique(all('[contenteditable="true"],textarea[placeholder*="正文"]'), '正文')
    const actualBody = body instanceof HTMLTextAreaElement ? body.value : body.innerText
    const normalize = (value: string) => value.replace(/\s+/g, ' ').trim()

    if (title.value !== payload.title || normalize(actualBody) !== normalize(payload.body)) {
      throw new Error('发布前内容核对不一致')
    }

    if (/上传中|上传失败|正在上传/.test(document.body.innerText)) { throw new Error('图片尚未完成上传') }

    if (all('.img-container .uploading,.img-container[aria-busy="true"]').length) { throw new Error('图片尚未完成上传或处理') }
    const previews = all('[class*="upload"] img,[class*="image-list"] img').filter(img => (img as HTMLImageElement).naturalWidth > 0)

    if (previews.length < payload.asset_ids.length) { throw new Error('尚未核对全部图片缩略图') }

    return { ready: true }
  }

  const handlers: Record<string, () => unknown> = {
    'open-note': () => {
      const matches = items().filter(element => identifier(element) === payload.target)

      if (matches.length !== 1) { return { opened: false, reason: '目标笔记已不在当前候选页，请重新读取候选' } }
      const link = noteLink(matches[0])

      if (!link) { return { opened: false, reason: '目标笔记入口不可用，请重新读取候选' } }
      link.click()

      return { opened: payload.target }
    },
    'open-messages': () => {
      const entries = all('a,button,[role="button"]').filter(element => {
        const label = element.getAttribute('aria-label') || element.getAttribute('title') || text(element)
        const href = element.getAttribute('href')
        const url = href ? new URL(href, location.href) : null

        if (url && (url.origin !== location.origin || url.pathname === '/notification')) { return false }

        return /^(私信|消息|聊天)$/.test(label) || url?.pathname === '/im'
      }).filter(element => !all('a,button,[role="button"]', element).some(child => /^(私信|消息|聊天)$/.test(text(child))))

      if (entries.length !== 1) { return { opened: false, reason: '当前网页没有唯一可确认的私信入口，请在网页检查消息功能' } }
      entries[0].click()

      return { opened: true }
    },
    inventory: () => {
      const list = items()
        .map(element => ({
          id: identifier(element),
          text: text(element).slice(0, 2000),
          url:
            payload.kind === 'comment'
              ? noteLink(element)?.href
              : element.querySelector<HTMLAnchorElement>('a[href*="/user/profile/"]')?.href,
          inbound: payload.kind === 'dm' && element.getAttribute('data-direction') === 'incoming',
          follows_me: payload.kind === 'follow' && inventory().followsMe(element),
          already_following: payload.kind === 'follow' && inventory().alreadyFollowing(element)
        }))
        .filter(item => item.id)

      if (!list.length && !inventory().empty) {
        throw new Error('未识别到稳定条目或明确空列表，页面结构需要人工核对')
      }

      return { items: list, url: location.href, evidence: list.length ? '页面可见条目' : '页面明确显示暂无条目' }
    },
    'click-label': () => {
      button(payload.label).click()

      return { ok: true }
    },
    upload: () => {
      const inputs = Array.from(document.querySelectorAll<HTMLInputElement>('input[type="file"]')).filter(input =>
        /image|\.(png|jpe?g|webp)/i.test(input.accept || '')
      )

      const input = unique(inputs, '图片上传框') as HTMLInputElement
      const transfer = new DataTransfer()

      for (const asset of payload.assets) {
        const bytes = Uint8Array.from(atob(asset.data), c => c.charCodeAt(0))

        const mime = asset.name.toLowerCase().endsWith('.png')
          ? 'image/png'
          : asset.name.toLowerCase().endsWith('.webp')
            ? 'image/webp'
            : 'image/jpeg'

        transfer.items.add(new File([bytes], asset.name, { type: mime }))
      }

      input.files = transfer.files
      input.dispatchEvent(new Event('change', { bubbles: true }))

      return { count: input.files.length }
    },
    'fill-post': () => {
      const title = unique(all('input[placeholder*="标题"],textarea[placeholder*="标题"]'), '标题')
      const body = unique(all('[contenteditable="true"],textarea[placeholder*="正文"]'), '正文')
      setText(title, payload.title)
      setText(body, payload.body)

      return { ok: true }
    },
    'validate-post': validatePost,
    'commit-post': () => {
      validatePost()
      publishControl(true, payload.title)

      return { state: 'submitted' }
    },
    'post-result': () => {
      const body = document.body.innerText || ''

      const published = all('a[href*="/explore/"]', document).filter(e =>
        /查看笔记|查看作品/.test(text(e))
      ) as HTMLAnchorElement[]

      if (/发布成功/.test(body) && published.length === 1) {
        return { state: 'published', evidence: '平台发布成功并提供笔记链接', url: published[0].href }
      }

      if (/发布成功|提交成功|审核中/.test(body)) {
        return { state: 'submitted', evidence: body.slice(0, 1500), url: location.href }
      }

      return { state: 'unknown', evidence: '未获得平台提交确认', url: location.href }
    },
    'verify-post': () => {
      const title = all('#detail-title,.note-detail .title').map(text)
      const body = all('#detail-desc,.note-detail .desc').map(text)

      const author = all('.author a[href*="/user/profile/"],a.username[href*="/user/profile/"]').some(e =>
        new URL((e as HTMLAnchorElement).href).pathname.endsWith(`/user/profile/${payload.account_id}`)
      )

      const normalize = (value: string) => value.replace(/\s+/g, '')

      if (
        /\/explore\/[^/]+/.test(location.pathname) &&
        author &&
        title.includes(payload.content.title) &&
        body.some(value => normalize(value) === normalize(payload.content.body))
      ) {
        return { state: 'published', evidence: '公开笔记链接、作者及全文与执行记录一致', url: location.href }
      }

      return { state: 'unknown', evidence: '没有取得与账号及内容一致的公开笔记证据', url: location.href }
    },
    'prepare-interaction': () => {
      if (payload.kind === 'comment' && !inventory().matchesNote(payload.target)) { throw new Error('当前笔记与目标不一致，未填写评论') }
      const root = payload.kind === 'comment' ? document.body : findItem()

      if (payload.kind === 'follow') {
        if (!inventory().followsMe(root)) {
          throw new Error('无法确认对方关注了当前账号')
        }

        return { ready: true }
      }

      if (payload.kind === 'reply') {
        button('回复', root).click()
      }

      const editor = unique(
        all('textarea,input[placeholder*="评论"],[contenteditable="true"]', payload.kind === 'dm' ? document : root),
        '回复输入框'
      )

      setText(editor, payload.text)

      const before_count = all('[data-message-id],.comment-content,.content', root).filter(
        e => text(e) === payload.text
      ).length

      return { ready: true, before_count }
    },
    'commit-interaction': () => {
      if (payload.kind === 'comment' && !inventory().matchesNote(payload.target)) { throw new Error('当前笔记与目标不一致，未提交评论') }
      const root = payload.kind === 'comment' ? document.body : findItem()

      if (payload.kind === 'follow') {
        if (!inventory().followsMe(root)) {
          throw new Error('对方关注状态发生变化')
        }

        button('回关', root).click()
      } else {
        const editor = unique(
          all('textarea,input[placeholder*="评论"],[contenteditable="true"]', payload.kind === 'dm' ? document : root),
          '回复输入框'
        ) as HTMLInputElement

        if ((editor.value ?? text(editor)) !== payload.text) {
          throw new Error('发送前文本核对不一致')
        }

        button('发送', payload.kind === 'dm' ? document : root).click()
      }

      return { state: 'submitted' }
    },
    'interaction-result': () => {
      const root = payload.kind === 'comment' ? document.body : findItem()

      const sent =
        payload.kind === 'follow'
          ? inventory().alreadyFollowing(root)
          : typeof payload.before_count === 'number' &&
            all('[data-message-id],.comment-content,.content', root).filter(e => text(e) === payload.text).length >
              payload.before_count

      return sent
        ? { state: 'confirmed', evidence: text(root).slice(0, 2000), url: location.href }
        : { state: 'unknown', evidence: '未核对到动作后的状态' }
    }
  }

  const handler = handlers[operation]

  if (!handler) {
    throw new Error('不支持的网页动作')
  }

  return handler()
}
