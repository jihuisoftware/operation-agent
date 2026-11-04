import { xhsInteractionDom } from './interaction-dom'
import { xhsPublishControl } from './publish-control'

/** Read-only readiness checks, serialized into the same isolated execution page. */
export function xhsReady(request: { phase: string; payload: Record<string, any> }, publishControl = xhsPublishControl, interactionDom = xhsInteractionDom) {
  const { phase, payload } = request

  const visible = (element: Element) => {
    if (element.closest('[aria-hidden="true"],[hidden]')) { return false }
    const rect = element.getBoundingClientRect()

    return rect.bottom >= 0 && rect.right >= 0 && Boolean((element as HTMLElement).offsetWidth || (element as HTMLElement).offsetHeight || element.getClientRects().length)
  }

  const all = (selector: string) => Array.from(document.querySelectorAll<HTMLElement>(selector)).filter(visible)

  if (!document.body) { return { ready: false } }
  const body = document.body.innerText || ''

  if (/安全验证|拖动滑块/.test(body)) { throw new Error('页面要求人工安全验证') }

  if (phase === 'inventory' || phase === 'interaction') {
    const view = interactionDom(payload.kind)

    if (view.unavailable) { return { ready: false, unavailable: true, reason: '目标页面访问受限、已失效或要求重新登录' } }

    if (phase === 'inventory') {
      return { ready: view.rows.length > 0 || view.empty, reason: view.blank ? '页面仍为空白，尚未取得消息或列表内容' : '未识别到稳定条目或明确空列表，请检查当前页面' }
    }

    return { ready: payload.kind === 'comment'
      ? view.matchesNote(payload.target) && all('#detail-desc,.note-detail .desc').length > 0
      : view.rows.some(row => view.identifier(row) === payload.target), reason: '目标条目尚未加载或无法核对身份' }
  }

  const handlers: Record<string, () => boolean> = {
    publish: () => publishControl(false, payload.title).ready,
    label: () => all('button,[role="button"],a,span').some(element => element.textContent?.trim() === payload.label),
    upload: () => Array.from(document.querySelectorAll<HTMLInputElement>('input[type="file"]')).some(input => /image|\.(png|jpe?g|webp)/i.test(input.accept)),
    post: () => {
      if (/上传失败/.test(body)) { throw new Error('图片上传失败') }

      return !/上传中|正在上传/.test(body) &&
        all('.img-container .uploading,.img-container[aria-busy="true"]').length === 0 &&
        all('input[placeholder*="标题"],textarea[placeholder*="标题"]').length === 1 &&
        all('[contenteditable="true"],textarea[placeholder*="正文"]').length === 1 &&
        all('[class*="upload"] img,[class*="image-list"] img').filter(image => (image as HTMLImageElement).naturalWidth > 0).length >= payload.content.asset_ids.length
    },
  }

  return { ready: handlers[phase]?.() === true }
}
