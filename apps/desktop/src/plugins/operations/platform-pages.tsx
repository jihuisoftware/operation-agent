import { Button, useValue } from '@hermes/plugin-sdk'
import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react'

import { browserDockStyle } from './browser-dock'
import { BrowserToolbar } from './browser-toolbar'
import { loginPlatform } from './login-page'
import { $loginNavigation, $loginRequest, type LoginOwner, type LoginRequest } from './login-state'
import { $showOperationsBrowser } from './state'
import type { Api, Guest } from './types'
import { useLoginObservation } from './use-login-observation'
import { useOperationsGuest } from './use-operations-guest'

export const LOGIN_PAGES = [
  { id: 'xiaohongshu', name: '小红书', url: 'https://www.xiaohongshu.com/explore' },
  { id: 'zhihu', name: '知乎', url: 'https://www.zhihu.com/' },
  { id: 'bilibili', name: 'B 站', url: 'https://www.bilibili.com/' },
  { id: 'wechat', name: '微信公众号后台', url: 'https://mp.weixin.qq.com/' },
  { id: 'douyin', name: '抖音', url: 'https://www.douyin.com/' }
]

export function usePlatformPages(primary: Guest) {
  const [opened, setOpened] = useState(['xiaohongshu'])
  const [active, setActive] = useState('xiaohongshu')
  const guests = useRef(new Map<string, Guest>())

  const register = useCallback((platform: string, guest: Guest) => {
    guests.current.set(platform, guest)

    return () => { guests.current.delete(platform) }
  }, [])

  const openPage = useCallback(async (request: LoginRequest) => {
    const page = LOGIN_PAGES.find(p => p.id === request.platform)

    if (!page || loginPlatform(request.url) !== page.id) { throw new Error('平台登录地址不匹配') }
    setOpened(previous => previous.includes(page.id) ? previous : [...previous, page.id])
    setActive(page.id)
    const guest = page.id === 'xiaohongshu' ? primary : guests.current.get(page.id)

    // Reopening a platform must not reload an in-progress QR code or another logged-in page.
    if (guest?.isConnected && loginPlatform(guest.getURL()) !== page.id) {
      await guest.loadURL(page.url)
    }
  }, [primary])

  return { opened, active, select: setActive, openPage, register }
}

interface PlatformPageTabsProps {
  owner: LoginOwner
  active: string
  opened: string[]
  select: (platform: string) => void
}

export function PlatformPageTabs({ owner, active, opened, select }: PlatformPageTabsProps) {
  const navigating = useValue($loginNavigation)

  return <nav aria-label="平台页面" className="flex shrink-0 flex-wrap gap-1 border-b p-2">
    {LOGIN_PAGES.map(page => <Button
      aria-pressed={active === page.id}
      disabled={Boolean(navigating)}
      key={page.id}
      onClick={() => {
        if ($loginNavigation.get()) { return }

        if (opened.includes(page.id)) { select(page.id) } else {
          $loginRequest.set({ owner, platform: page.id, url: page.url, id: crypto.randomUUID() })
        }
      }}
      size="sm"
      variant={active === page.id ? 'secondary' : 'ghost'}
    >{page.name}</Button>)}
  </nav>
}

interface PlatformPageFrameProps {
  name: string
  visible: boolean
  children: ReactNode
}

export function PlatformPageFrame({ name, visible, children }: PlatformPageFrameProps) {
  const surface = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const focused = document.activeElement

    if (!visible && focused instanceof HTMLElement && surface.current?.contains(focused)) { focused.blur() }
  }, [visible])

  return <div
    aria-hidden={!visible || undefined}
    aria-label={`${name}页面`}
    className="flex min-h-0 flex-1 flex-col"
    inert={!visible || undefined}
    ref={surface}
    role="region"
    style={visible ? undefined : browserDockStyle(false)}
  >{children}</div>
}

interface PlatformLoginPageProps {
  owner: LoginOwner
  platform: string
  visible: boolean
  worker: string
  api: Api
  takeOver: () => Promise<void>
  release: () => Promise<void>
  register: (platform: string, guest: Guest) => () => void
}

export function PlatformLoginPage({ owner, platform, visible, worker, api, takeOver, release, register }: PlatformLoginPageProps) {
  const page = LOGIN_PAGES.find(p => p.id === platform)!
  const container = useRef<HTMLDivElement>(null)
  const { guest, loading, error, reopen } = useOperationsGuest(owner, container, page.url)
  const [status, setStatus] = useState('登录状态会自动检查；切换平台后仍保留此页面')
  useEffect(() => register(platform, guest), [register, platform, guest])
  useLoginObservation({ api, guest, worker, platform, onStatus: setStatus })

  const run = (action: () => Promise<void>) => { void action().catch(reason => setStatus(String(reason))) }

  return <PlatformPageFrame name={page.name} visible={visible}>
    <BrowserToolbar
      error={error}
      hide={() => $showOperationsBrowser.set(false)}
      loading={loading}
      login={() => run(async () => { await takeOver(); await reopen() })}
      platformName={page.name}
      release={() => run(async () => { await release(); setStatus('已结束接管，网页动作按后续排期执行') })}
      reopen={() => run(async () => { await takeOver(); await reopen() })}
      status={status}
      takeOver={() => run(async () => { await takeOver(); setStatus('网页已接管，完成后点击结束接管') })}
    />
    <div className="min-h-0 flex-1" ref={container} />
  </PlatformPageFrame>
}
