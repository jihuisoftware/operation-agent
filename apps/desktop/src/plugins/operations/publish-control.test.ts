import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { xhsPage } from './page'
import { xhsReady } from './page-ready'

const payload = { title: '测试稿', body: '已核对正文', asset_ids: [] }

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(100)
  Object.defineProperty(HTMLElement.prototype, 'innerText', { configurable: true, get() { return this.textContent || '' } })
  document.body.innerHTML = '<input placeholder="标题"><textarea placeholder="正文"></textarea>'
  xhsPage({ operation: 'fill-post', payload })
})
afterEach(() => { document.body.innerHTML = ''; vi.restoreAllMocks() })

function control() {
  const element = document.createElement('xhs-publish-btn')
  element.attachShadow({ mode: 'closed' }).innerHTML = '<button>暂存离开</button><button>发布</button>'

  for (const [name, value] of Object.entries({ 'is-publish': 'true', 'submit-text': '发布', 'submit-disabled': 'false', 'submit-loading': 'false' })) {
    element.setAttribute(name, value)
  }

  document.body.append(element)

  return element
}

it('uses the publish event of the closed-shadow control after validating the exact draft', () => {
  const element = control()
  const published = vi.fn()
  const saved = vi.fn()
  element.addEventListener('publish', published)
  element.addEventListener('save', saved)
  expect(element.shadowRoot).toBeNull()
  expect(xhsReady({ phase: 'publish', payload })).toEqual({ ready: true })
  expect(xhsPage({ operation: 'commit-post', payload })).toEqual({ state: 'submitted' })
  expect(published).toHaveBeenCalledOnce()
  expect(saved).not.toHaveBeenCalled()
})

it.each(['disabled', 'loading', 'duplicate', 'changed'] as const)('refuses a custom submit when %s', condition => {
  const element = control()
  const published = vi.fn()
  element.addEventListener('publish', published)

  if (condition === 'disabled') { element.setAttribute('submit-disabled', 'true') }

  if (condition === 'loading') { element.setAttribute('submit-loading', 'true') }

  if (condition === 'duplicate') { control() }

  if (condition === 'changed') { document.querySelector('textarea')!.value = '被修改的正文' }

  if (condition !== 'changed') { expect(xhsReady({ phase: 'publish', payload })).toEqual({ ready: false }) }

  expect(() => xhsPage({ operation: 'commit-post', payload })).toThrow()
  expect(published).not.toHaveBeenCalled()
})

it.each(['<div class="uploading"></div>', ''])('waits for image upload/processing even when the local thumbnail is already decoded: %s', spinner => {
  control()
  vi.spyOn(HTMLImageElement.prototype, 'naturalWidth', 'get').mockReturnValue(100)
  const container = document.createElement('div')
  container.className = 'image-list img-container'
  container.setAttribute('aria-busy', String(!spinner))
  container.innerHTML = `<img src="blob:preview">${spinner}`
  document.body.append(container)
  const content = { ...payload, asset_ids: ['cover'] }
  expect(xhsReady({ phase: 'post', payload: { content } })).toEqual({ ready: false })
  expect(() => xhsPage({ operation: 'commit-post', payload: content })).toThrow('图片尚未完成上传或处理')
  container.setAttribute('aria-busy', 'false')
  container.querySelector('.uploading')?.remove()
  expect(xhsReady({ phase: 'post', payload: { content } })).toEqual({ ready: true })
})
