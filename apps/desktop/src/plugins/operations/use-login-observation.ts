import { host } from '@hermes/plugin-sdk'
import { useEffect, useRef } from 'react'

import { inspectLoginPage, loginPlatform } from './login-page'
import { $loginStatusRevision, type LoginObservation } from './login-state'
import type { Api, Guest } from './types'

interface LoginObservationProps {
  api: Api
  guest: Guest
  worker: string
  platform: string
  onStatus: (status: string) => void
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

export function useLoginObservation({ api, guest, worker, platform, onStatus }: LoginObservationProps) {
  // API/owner callbacks can change while the same guest remains mounted and ready.
  const readyGuest = useRef<Guest | null>(null)

  // Readiness comes from guest lifecycle events, not mirrored React/atom state.
  // eslint-disable-next-line no-restricted-syntax
  useEffect(() => {
    let disposed = false
    let busy = false
    let generation = 0
    const problems = new Map<string, string>()
    const observations = new Map<string, string>()

    const observe = async () => {
      if (disposed || busy || readyGuest.current !== guest || !guest.isConnected) {
        return
      }

      const url = guest.getURL()

      if (loginPlatform(url) !== platform) {
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
          onStatus(`登录状态未同步：${String(error)}`)
        }
      } finally {
        busy = false
      }
    }

    const navigate = () => {
      generation += 1
      readyGuest.current = null
    }

    const inspect = () => {
      void observe().catch(error => {
        if (!disposed) {
          onStatus(`登录页面暂不可读取：${String(error)}`)
        }
      })
    }

    const ready = () => {
      readyGuest.current = guest
      inspect()
    }

    guest.addEventListener('did-start-loading', navigate)
    guest.addEventListener('dom-ready', ready)
    guest.addEventListener('did-stop-loading', ready)
    guest.addEventListener('did-navigate-in-page', ready)
    const timer = setInterval(inspect, 2000)

    return () => {
      disposed = true
      clearInterval(timer)
      guest.removeEventListener('did-start-loading', navigate)
      guest.removeEventListener('dom-ready', ready)
      guest.removeEventListener('did-stop-loading', ready)
      guest.removeEventListener('did-navigate-in-page', ready)
    }
  }, [api, guest, worker, platform, onStatus])
}
