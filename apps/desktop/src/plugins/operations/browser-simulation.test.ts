import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { executeBrowser } from './browser'
import type { Api, BrowserCommand, Guest } from './types'

beforeEach(() => {
  vi.useFakeTimers()
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(100)
  vi.spyOn(HTMLImageElement.prototype, 'naturalWidth', 'get').mockReturnValue(100)
  Object.defineProperty(HTMLElement.prototype, 'innerText', { configurable: true, get() { return this.textContent || '' } })
  vi.stubGlobal('DataTransfer', class {
    files: File[] = []
    items = { add: (file: File) => this.files.push(file) }
  })
})
afterEach(() => { document.body.innerHTML = ''; vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers() })

function fixture(mode: 'success' | 'pause' | 'disconnect') {
  let url = 'about:blank'
  let paused = false
  let submissions = 0
  const events = new EventTarget()

  const guest = {
    addEventListener: events.addEventListener.bind(events),
    removeEventListener: events.removeEventListener.bind(events),
    getURL: () => url,
    loadURL: vi.fn(async (next: string) => {
      url = next
      vi.stubGlobal('location', new URL(next))

      if (next.includes('/explore')) {
        document.body.innerHTML = '<nav><a href="https://www.xiaohongshu.com/user/profile/me">我</a></nav>'
      } else {
        document.body.innerHTML = '<button>上传图文</button><input type="file" accept="image/png"><input placeholder="标题"><textarea placeholder="正文"></textarea><button id="submit">发布</button><div class="image-list"></div>'
        const upload = document.querySelector<HTMLInputElement>('input[type=file]')!
        Object.defineProperty(upload, 'files', { writable: true, value: [] })
        upload.addEventListener('change', () => {
          setTimeout(() => {
            document.querySelector('.image-list')!.innerHTML = '<img src="cover.png">'

            if (mode === 'pause') { paused = true }
          }, 4500)
        })
        document.querySelector('#submit')!.addEventListener('click', () => {
          submissions += 1
          setTimeout(() => {
            document.body.innerHTML = '<p>发布成功</p><a href="https://www.xiaohongshu.com/explore/note">查看笔记</a>'
          }, 3000)
        })
      }

      events.dispatchEvent(new Event('did-stop-loading'))
    }),
    executeJavaScript: vi.fn(async (code: string) => {
      if (mode === 'disconnect' && submissions) { throw new Error('提交后断线') }

      return (0, eval)(code)
    })
  } as unknown as Guest

  const api = (async (path: string) => path === '/policy'
    ? { version: 1, policy: { account_id: '', topic: '测试', enabled: true, paused } }
    : { name: 'cover.png', data: '' }) as Api

  const command: BrowserCommand = { id: 'simulated', kind: 'publish', expires: Date.now() / 1000 + 120, payload: {
    account_id: 'me', policy_version: 1, content: { title: '测试图文', body: '来自可追溯资料的摘要', asset_ids: ['cover'] }
  } }

  return { guest, api, command, submissions: () => submissions }
}

it.each(['success', 'pause', 'disconnect'] as const)('executes the actual DOM adapter with delayed image and receipt: %s', async mode => {
  const test = fixture(mode)
  const pending = executeBrowser(test.command, test.guest, test.api)
  await vi.runAllTimersAsync()
  const result = await pending
  expect(result.state).toBe({ success: 'published', pause: 'blocked', disconnect: 'unknown' }[mode])
  expect(test.submissions()).toBe(mode === 'pause' ? 0 : 1)

  if (mode === 'success') { expect(result.url).toBe('https://www.xiaohongshu.com/explore/note') }
})
