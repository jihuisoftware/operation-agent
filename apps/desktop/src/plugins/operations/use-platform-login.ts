import { type CronBlueprintOwner, host, useValue } from '@hermes/plugin-sdk'
import { useEffect, useRef } from 'react'

import { inspectLoginPage, loginPlatform } from './login-page'
import {
  $loginNavigation,
  $loginRequest,
  $loginStatusRevision,
  $loginWorker,
  type LoginObservation,
  sameLoginOwner
} from './login-state'
import { $operationsWorkerStatus, $showOperationsBrowser } from './state'
import type { Api, Guest } from './types'

interface LoginMonitorProps {
  api: Api
  guest: Guest
  owner: CronBlueprintOwner
  worker: string
  takeOver: () => Promise<void>
}

async function inspectWithDeadline(guest: Guest, platform: string): Promise<LoginObservation> {
  let timer: ReturnType<typeof setTimeout> | undefined

  try {
    return await Promise.race([
      guest.executeJavaScript(
        `(${inspectLoginPage.toString()})(${JSON.stringify(platform)})`
      ) as Promise<LoginObservation>,
      new Promise<LoginObservation>((_, reject) => {
        timer = setTimeout(() => reject(new Error('登录检查超时')), 5000)
      })
    ])
  } finally {
    clearTimeout(timer)
  }
}

export function usePlatformLogin({ api, guest, owner, worker, takeOver }: LoginMonitorProps) {
  const request = useValue($loginRequest)
  const handledRequests = useRef(new Set<string>())

  useEffect(() => {
    $loginWorker.set({ owner, worker })
    let disposed = false
    let busy = false
    let generation = 0
    let pageReady = false
    const problems = new Map<string, string>()
    const observations = new Map<string, string>()

    const observe = async () => {
      if (disposed || busy || !pageReady || !guest.isConnected) {
        return
      }

      const url = guest.getURL()
      const platform = loginPlatform(url)

      if (!platform) {
        return
      }

      const started = generation
      busy = true

      try {
        let observation: LoginObservation

        try {
          observation = await inspectWithDeadline(guest, platform)
        } catch {
          observation = { state: 'unknown', account_id: '' }
        }

        if (disposed || started !== generation || guest.getURL() !== url) {
          return
        }

        const signature = JSON.stringify([started, observation.state, observation.account_id])

        // Report state changes; an unchanged page is not a new login confirmation.
        if (observations.get(platform) === signature) {
          return
        }

        await api('/platforms/observe', { worker, platform, ...observation })
        observations.set(platform, signature)

        if (!disposed) {
          $loginStatusRevision.set($loginStatusRevision.get() + 1)
        }

        if (disposed) {
          return
        }

        if (
          ['logged_out', 'verification'].includes(observation.state) &&
          problems.get(platform) !== observation.state
        ) {
          host.notify({ kind: 'info', message: '平台页面需要登录或验证，请到“平台登录状态”处理后再执行重复任务。' })
        }

        problems.set(platform, observation.state)
      } catch (error) {
        if (!disposed) {
          $operationsWorkerStatus.set(`登录状态未同步：${String(error)}`)
        }
      } finally {
        busy = false
      }
    }

    const navigate = () => {
      generation += 1
      pageReady = false
    }

    const inspect = () => {
      void observe().catch(error => {
        if (!disposed) {
          $operationsWorkerStatus.set(`登录页面暂不可读取：${String(error)}`)
        }
      })
    }

    const ready = () => {
      pageReady = true
      inspect()
    }

    guest.addEventListener('did-start-loading', navigate)
    guest.addEventListener('dom-ready', ready)
    guest.addEventListener('did-navigate-in-page', ready)
    const timer = setInterval(inspect, 2000)

    return () => {
      disposed = true
      clearInterval(timer)
      guest.removeEventListener('did-start-loading', navigate)
      guest.removeEventListener('dom-ready', ready)
      guest.removeEventListener('did-navigate-in-page', ready)

      if ($loginWorker.get()?.worker === worker) {
        $loginWorker.set(null)
      }
    }
  }, [api, guest, owner, worker])

  useEffect(() => {
    if (!request || !sameLoginOwner(request.owner, owner) || handledRequests.current.has(request.id)) {
      return
    }

    handledRequests.current.add(request.id)
    let disposed = false
    $loginNavigation.set(request.id)

    const open = async () => {
      try {
        if (loginPlatform(request.url) !== request.platform) {
          throw new Error('平台登录地址不匹配')
        }

        $showOperationsBrowser.set(true)
        $operationsWorkerStatus.set('正在暂停自动动作并打开登录页面…')
        await takeOver()

        if (disposed || !guest.isConnected) {
          return
        }

        await api('/platforms/observe', { worker, platform: request.platform, state: 'unknown', account_id: '' })

        if (disposed) {
          return
        }

        await guest.loadURL(request.url)
      } catch (error) {
        if (!disposed) {
          $operationsWorkerStatus.set(String(error))
        }
      } finally {
        if ($loginNavigation.get() === request.id) {
          $loginNavigation.set(null)
        }

        if ($loginRequest.get()?.id === request.id) {
          $loginRequest.set(null)
        }
      }
    }

    void open()

    return () => {
      disposed = true

      if ($loginNavigation.get() === request.id) {
        $loginNavigation.set(null)
      }

      if ($loginRequest.get()?.id === request.id) {
        $loginRequest.set(null)
      }
    }
  }, [api, guest, owner, request, takeOver, worker])
}
