/** Serialized with the page adapter; uses the creator component's public event contract. */
export function xhsPublishControl(submit = false, expectedTitle?: string) {
  const visible = (element: HTMLElement) => {
    const rect = element.getBoundingClientRect()

    return !element.closest('[aria-hidden="true"],[hidden]') && rect.bottom >= 0 && rect.right >= 0 &&
      Boolean(element.offsetWidth || element.offsetHeight || element.getClientRects().length)
  }

  const selector = 'button,[role="button"],a,span'

  const ordinary = Array.from(document.querySelectorAll<HTMLElement>(selector)).filter(element =>
    visible(element) && element.textContent?.trim() === '发布' &&
    !Array.from(element.querySelectorAll<HTMLElement>(selector)).some(child => visible(child) && child.textContent?.trim() === '发布')
  )

  const custom = Array.from(document.querySelectorAll<HTMLElement>('xhs-publish-btn')).filter(visible)
  const controls = [...ordinary, ...custom]
  const element = controls[0]

  const previewMatches = () => {
    if (!custom.length || expectedTitle === undefined) { return true }
    const titles = document.querySelectorAll('.image-preview .scroll-container > .title')

    return titles.length === 1 && titles[0].textContent?.trim() === expectedTitle
  }

  const enabled = previewMatches() && controls.length === 1 && (custom.length === 1
    ? element.getAttribute('is-publish') === 'true' && element.getAttribute('submit-text') === '发布' &&
      element.getAttribute('submit-disabled') === 'false' && element.getAttribute('submit-loading') === 'false'
    : !element.matches(':disabled,[disabled],[aria-disabled="true"]'))

  if (submit) {
    if (!enabled) { throw new Error('发布控件未就绪、不可用或不唯一') }

    if (custom.length) {
      element.dispatchEvent(new CustomEvent('publish', { bubbles: true, composed: true }))
    } else {
      element.click()
    }
  }

  return { ready: enabled }
}
