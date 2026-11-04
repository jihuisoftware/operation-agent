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

function fixture(mode: 'success' | 'custom' | 'disabled' | 'pause' | 'disconnect') {
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

      if (next.endsWith('/explore/note')) {
        document.body.innerHTML = '<div class="author"><a href="https://www.xiaohongshu.com/user/profile/me">作者</a></div><div id="detail-title">测试图文</div><div id="detail-desc">来自可追溯资料的摘要</div><div class="swiper-slide"><img src="https://sns.xhscdn.com/cover.png"></div>'
      } else if (next.includes('/user/profile/me')) {
        document.body.innerHTML = '<p>暂无笔记</p>'
      } else if (next.includes('/note-manager')) {
        document.body.innerHTML = '<article class="note-card" data-note-id="note">已发布</article>'
      } else if (next.includes('/explore')) {
        document.body.innerHTML = '<nav><a href="https://www.xiaohongshu.com/user/profile/me">我</a></nav>'
      } else {
        document.body.innerHTML = '<button>上传图文</button><input type="file" accept="image/png"><input placeholder="标题"><textarea placeholder="正文"></textarea><button id="submit">发布</button><div class="image-list"></div>'
        const upload = document.querySelector<HTMLInputElement>('input[type=file]')!
        Object.defineProperty(upload, 'files', { writable: true, value: [] })
        upload.addEventListener('change', () => {
          setTimeout(() => {
            document.querySelector('.image-list')!.innerHTML = '<div class="img-container"><img src="cover.png"><div class="uploading"></div></div>'
            setTimeout(() => document.querySelector('.uploading')?.remove(), 4000)

            if (mode === 'pause') { paused = true }
          }, 4500)
        })
        let submit = document.querySelector('#submit')!
        const custom = mode === 'custom' || mode === 'disabled'

        if (custom) {
          const host = document.createElement('xhs-publish-btn')
          host.attachShadow({ mode: 'closed' }).innerHTML = '<button>发布</button>'

          for (const [name, value] of Object.entries({ 'is-publish': 'true', 'submit-text': '发布', 'submit-disabled': String(mode === 'disabled'), 'submit-loading': 'false' })) {
            host.setAttribute(name, value)
          }

          submit.replaceWith(host)
          submit = host
          document.body.insertAdjacentHTML('beforeend', '<div class="image-preview"><div class="scroll-container"><div class="title"></div></div></div>')
          document.querySelector('input[placeholder="标题"]')!.addEventListener('input', event => {
            const title = (event.target as HTMLInputElement).value
            setTimeout(() => { document.querySelector('.image-preview .title')!.textContent = title }, 300)
          })
        }

        submit.addEventListener(custom ? 'publish' : 'click', () => {
          expect(document.querySelector('.uploading')).toBeNull()

          if (custom) { expect(document.querySelector('.image-preview .title')?.textContent).toBe('测试图文') }
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
    : path === '/worker/verify-images' ? { state: 'matched' } : { name: 'cover.png', data: '' }) as Api

  const command: BrowserCommand = { id: 'simulated', kind: 'publish', expires: Date.now() / 1000 + 120, payload: {
    account_id: 'me', policy_version: 1, content: { title: '测试图文', body: '来自可追溯资料的摘要', asset_ids: ['cover'] }
  } }

  return { guest, api, command, submissions: () => submissions }
}

it.each(['success', 'custom', 'disabled', 'pause', 'disconnect'] as const)('executes the actual DOM adapter with delayed image and receipt: %s', async mode => {
  const test = fixture(mode)
  const pending = executeBrowser(test.command, test.guest, test.api)
  await vi.runAllTimersAsync()
  const result = await pending
  expect(result.state).toBe({ success: 'submitted', custom: 'submitted', disabled: 'blocked', pause: 'blocked', disconnect: 'unknown' }[mode])
  expect(test.submissions()).toBe(mode === 'pause' || mode === 'disabled' ? 0 : 1)

  if (mode === 'success') { expect(result.url).toBe('https://www.xiaohongshu.com/explore/note') }
})

it('opens the actual search card before submitting one comment to the verified note', async () => {
  let url = 'about:blank'
  let sent = 0
  const events = new EventTarget()

  const guest = {
    addEventListener: events.addEventListener.bind(events), removeEventListener: events.removeEventListener.bind(events),
    getURL: () => url,
    loadURL: vi.fn(async (next: string) => {
      url = next
      vi.stubGlobal('location', new URL(next))
      document.body.innerHTML = '<nav><a href="https://www.xiaohongshu.com/user/profile/me">我</a></nav>'

      if (next.includes('/search_result')) {
        document.body.innerHTML += '<section class="note-item"><a id="card" href="https://www.xiaohongshu.com/explore/target?xsec_token=kept">目标笔记</a></section>'
        document.querySelector('#card')!.addEventListener('click', event => {
          event.preventDefault()
          url = 'https://www.xiaohongshu.com/explore/target?xsec_token=kept'
          vi.stubGlobal('location', new URL(url))
          document.body.innerHTML = '<div id="detail-desc">目标笔记</div><textarea placeholder="评论"></textarea><button>发送</button>'
          document.querySelector('button')!.addEventListener('click', () => {
            sent += 1
            const posted = document.createElement('div')
            posted.className = 'comment-content'
            posted.textContent = (document.querySelector('textarea') as HTMLTextAreaElement).value
            document.body.append(posted)
          })
        })
      }

      events.dispatchEvent(new Event('did-stop-loading'))
    }),
    executeJavaScript: vi.fn(async (code: string) => (0, eval)(code))
  } as unknown as Guest

  const api = (async () => ({ version: 1, policy: { enabled: true, paused: false, account_id: 'me', topic: '测试' } })) as Api

  const result = executeBrowser({ id: 'comment', kind: 'interact', expires: Date.now() / 1000 + 120,
    payload: { kind: 'comment', policy_version: 1, account_id: 'me', target: 'note:target', text: '有依据的回复',
      inventory_url: 'https://www.xiaohongshu.com/search_result?keyword=test', item: { url: 'https://www.xiaohongshu.com/explore/target' } } }, guest, api)

  await vi.runAllTimersAsync()
  expect(await result).toMatchObject({ state: 'confirmed' })
  expect(sent).toBe(1)
  expect(guest.loadURL).not.toHaveBeenCalledWith('https://www.xiaohongshu.com/explore/target')
})

it('reads actual search DOM during an account diagnostic without any submit path', async () => {
  const events = new EventTarget()
  let url = 'about:blank'

  const guest = {
    addEventListener: events.addEventListener.bind(events), removeEventListener: events.removeEventListener.bind(events),
    getURL: () => url,
    loadURL: async (next: string) => {
      url = next
      vi.stubGlobal('location', new URL(next))
      document.body.innerHTML = '<nav><a href="https://www.xiaohongshu.com/user/profile/me">我</a></nav>'

      if (next.includes('/search_result')) {
        document.body.innerHTML += '<section class="note-item"><a href="https://www.xiaohongshu.com/explore/readonly-note">候选笔记</a></section>'
      }

      events.dispatchEvent(new Event('dom-ready'))
    },
    executeJavaScript: async (code: string) => (0, eval)(code)
  } as unknown as Guest

  const api = (async () => ({ version: 1, policy: { enabled: true, paused: false, account_id: 'me', topic: '测试' } })) as Api

  const pending = executeBrowser({ id: 'read-only-search', kind: 'account', expires: Date.now() / 1000 + 120,
    payload: { policy_version: 1, resume_probe: true, readonly_inventory: 'comment', keywords: ['测试'] } }, guest, api)

  await vi.runAllTimersAsync()
  expect(await pending).toMatchObject({ state: 'logged_in', probe: 'account_and_search', items: [{ id: 'note:readonly-note' }] })
})

it('separates a slow proxy page load from the script execution budget', async () => {
  const events = new EventTarget()
  let url = 'about:blank'
  let loading = false
  let loaded = Promise.resolve()
  const dispatchedWhileLoading: boolean[] = []

  const guest = {
    addEventListener: events.addEventListener.bind(events), removeEventListener: events.removeEventListener.bind(events),
    getURL: () => url, isLoadingMainFrame: () => loading,
    loadURL: async (next: string) => {
      url = next
      loading = true
      vi.stubGlobal('location', new URL(next))
      document.body.innerHTML = '<nav><a href="https://www.xiaohongshu.com/user/profile/me">我</a></nav>'
      loaded = new Promise<void>(resolve => setTimeout(() => {
        loading = false
        events.dispatchEvent(new Event('did-stop-loading'))
        resolve()
      }, 45000))
      events.dispatchEvent(new Event('dom-ready'))
      await loaded
    },
    executeJavaScript: async (code: string) => {
      dispatchedWhileLoading.push(loading)
      await loaded

      return (0, eval)(code)
    }
  } as unknown as Guest

  const api = (async () => ({ version: 1, policy: { enabled: true, paused: false, account_id: 'me', topic: '测试' } })) as Api

  const result = executeBrowser({ id: 'slow-proxy', kind: 'account', expires: Date.now() / 1000 + 600,
    payload: { policy_version: 1, resume_probe: true } }, guest, api)

  await vi.advanceTimersByTimeAsync(46000)
  expect(await result).toMatchObject({ state: 'logged_in', account_id: 'me' })
  expect(dispatchedWhileLoading).toEqual([false])
})
