import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { executeBrowser } from './browser'
import { createBrowserTrace } from './browser-trace'
import type { Api, BrowserCommand, Guest } from './types'

beforeEach(() => {
  vi.useFakeTimers()
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(100)
  vi.spyOn(HTMLImageElement.prototype, 'naturalWidth', 'get').mockReturnValue(100)
  Object.defineProperty(HTMLElement.prototype, 'innerText', { configurable: true, get() { return this.textContent || '' } })
  vi.stubGlobal('DataTransfer', class { files: File[] = []; items = { add: (file: File) => this.files.push(file) } })
})
afterEach(() => { document.body.innerHTML = ''; vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers() })

function fixture(mode: 'published' | 'reviewing' | 'mismatch' | 'ambiguous' | 'image_unavailable' | 'verify' | 'manager_cover' | 'manager_unknown') {
  let url = 'about:blank'
  let sends = 0
  const events = new EventTarget()
  const records: any[] = []
  const note = (id: string) => `<section class="note-item"><a class="title" href="https://www.xiaohongshu.com/explore/${id}">测试图文</a></section>`

  const guest = {
    addEventListener: events.addEventListener.bind(events), removeEventListener: events.removeEventListener.bind(events), getURL: () => url,
    capturePage: vi.fn(async () => ({ resize: () => ({ toDataURL: () => 'data:image/png;base64,c2NyZWVuc2hvdA==' }) })),
    loadURL: vi.fn(async (next: string) => {
      url = next; vi.stubGlobal('location', new URL(next))

      if (next.endsWith('/explore')) {
        document.body.innerHTML = '<nav><a href="https://www.xiaohongshu.com/user/profile/me">我</a></nav>'
      } else if (next.includes('/user/profile/me')) {
        document.body.innerHTML = note('old') + (sends || mode === 'verify' ? note('new') : '') + (sends && mode === 'ambiguous' ? note('other') : '')
      } else if (next.endsWith('/explore/new')) {
        document.body.innerHTML = ''
        setTimeout(() => { document.body.innerHTML = `<div class="author"><a href="https://www.xiaohongshu.com/user/profile/me">作者</a></div><div id="detail-title">${mode === 'mismatch' ? '错误标题' : '测试图文'}</div><div id="detail-desc">实际正文需要完整核对</div><div class="swiper-slide"><img src="https://sns.xhscdn.com/cover.png"></div>` }, 500)
      } else if (next.includes('/note-manager')) {
        document.body.innerHTML = `<article class="note-card" ${mode === 'manager_cover' ? '' : 'data-note-id="new"'}><span class="note-card__title">测试图文</span><img src="https://sns.xhscdn.com/cover.png"><span>${mode === 'reviewing' ? '审核中' : mode === 'manager_unknown' ? '浏览 1' : '已发布'}</span></article>`
      } else {
        document.body.innerHTML = '<button>上传图文</button><input type="file" accept="image/png"><input placeholder="标题"><textarea placeholder="正文"></textarea><div class="image-list"></div><button id="submit">发布</button>'
        const upload = document.querySelector('input[type=file]')!
        Object.defineProperty(upload, 'files', { writable: true, value: [] })
        upload.addEventListener('change', () => { document.querySelector('.image-list')!.innerHTML = '<img src="cover.png">' })
        document.querySelector('#submit')!.addEventListener('click', () => { sends++; document.body.innerHTML = '<p>发布成功</p>' })
      }

      events.dispatchEvent(new Event('did-stop-loading'))
    }),
    executeJavaScript: vi.fn(async (code: string) => (0, eval)(code))
  } as unknown as Guest

  const api = (async (path: string, body: any) => {
    if (path === '/policy') { return { version: 1, policy: { enabled: true, paused: false, account_id: 'me' } } }

    if (path === '/worker/steps') { records.push(body);

 return {} }

    if (path === '/worker/verify-images') { return { state: mode === 'image_unavailable' ? 'incomplete' : 'matched', evidence: '图片核对结果' } }

    return { name: 'cover.png', data: '' }
  }) as Api

  const command: BrowserCommand = { id: 'command', kind: mode === 'verify' ? 'verify' : 'publish', expires: Date.now() / 1000 + 120, payload: {
    kind: 'publish', account_id: 'me', policy_version: 1,
    content: { title: '测试图文', body: '实际正文需要完整核对', asset_ids: ['cover'] },
    ...(mode === 'verify' ? { baseline: { ids: ['old'], account_id: 'me' }, previous_result: { state: 'submitted' } } : {})
  } }

  return { guest, api, command, records, sends: () => sends }
}

it.each(['published', 'reviewing', 'mismatch', 'ambiguous', 'image_unavailable', 'verify', 'manager_cover', 'manager_unknown'] as const)('discovers and verifies the actual new note without resubmission: %s', async mode => {
  const f = fixture(mode)
  const trace = createBrowserTrace(f.command, f.guest, f.api, 'desktop')
  const pending = executeBrowser(f.command, f.guest, f.api, undefined, trace, 'desktop')
  await vi.runAllTimersAsync()
  const submitted = await pending
  let result = submitted

  if (mode !== 'verify') {
    expect(submitted.state).toBe('submitted')
    expect(f.records.some(r => r.name === 'discover')).toBe(false)

    const verify: BrowserCommand = { ...f.command, id: 'independent-review', kind: 'verify', expires: Date.now() / 1000 + 180,
      payload: { ...f.command.payload, baseline: submitted.baseline, previous_result: submitted } }

    const reviewing = executeBrowser(verify, f.guest, f.api, undefined, createBrowserTrace(verify, f.guest, f.api, 'desktop'), 'desktop')
    await vi.runAllTimersAsync()
    result = await reviewing
  }

  expect(f.sends()).toBe(mode === 'verify' ? 0 : 1)
  expect(result.state).toBe(['published', 'verify', 'manager_cover'].includes(mode) ? 'published' : 'submitted')

  if (mode === 'ambiguous') {
    expect(result.error_code).toBe('AMBIGUOUS_PUBLICATION')
  } else {
    expect(result.note_id).toBe('new')
    expect(result.publication.content).toBe(mode === 'mismatch' ? 'mismatch' : mode === 'image_unavailable' ? 'incomplete' : 'matched')
    expect(result.publication.platform).toBe(mode === 'reviewing' ? 'reviewing' : mode === 'manager_unknown' ? 'unknown' : 'published')
  }

  expect(f.records.some(r => r.name === 'discover' && r.phase === 'completed')).toBe(true)

  if (mode === 'mismatch') { expect(f.records.some(r => r.phase === 'failed' && r.screenshot)).toBe(true) }
})
