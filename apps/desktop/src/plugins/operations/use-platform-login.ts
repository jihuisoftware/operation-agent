import { type CronBlueprintOwner, host, useValue } from '@hermes/plugin-sdk'
import { useEffect, useRef } from 'react'

import { loginPlatform } from './login-page'
import {
  $loginNavigation,
  $loginNavigationOwner,
  $loginRequest,
  $loginWorker,
  $loginWorkers,
  loginOwnerKey,
  type LoginRequest,
  sameLoginOwner
} from './login-state'
import { $operationsWorkerStatus, $showOperationsBrowser } from './state'
import { showAccount } from './workspace-state'

interface LoginMonitorProps {
  openPage: (request: LoginRequest) => Promise<void>
  owner: CronBlueprintOwner
  worker: string
  takeOver: () => Promise<void>
  onStatus?: (status: string) => void
}

export function usePlatformLogin({ openPage, owner, worker, takeOver, onStatus = $operationsWorkerStatus.set }: LoginMonitorProps) {
  const request = useValue($loginRequest)
  const handledRequests = useRef(new Set<string>())
  useEffect(() => {
    $loginWorker.set({ owner, worker })
    $loginWorkers.set({ ...$loginWorkers.get(), [loginOwnerKey(owner)]: worker })

    return () => {
      if ($loginWorker.get()?.worker === worker) { $loginWorker.set(null) }
      const entries = { ...$loginWorkers.get() }

      if (entries[loginOwnerKey(owner)] === worker) {
        delete entries[loginOwnerKey(owner)]
        $loginWorkers.set(entries)
      }
    }
  }, [owner, worker])

  useEffect(() => {
    if (!request || !sameLoginOwner(request.owner, owner) || handledRequests.current.has(request.id)) {
      return
    }

    handledRequests.current.add(request.id)
    let disposed = false
    $loginNavigation.set(request.id)
    $loginNavigationOwner.set(owner)

    const open = async () => {
      try {
        if (loginPlatform(request.url) !== request.platform) {
          throw new Error('平台登录地址不匹配')
        }

        $showOperationsBrowser.set(true)
        const account = (owner as { account_id?: string }).account_id

        if (account) { showAccount(owner, account) }
        onStatus('正在暂停自动动作并打开登录页面…')
        await takeOver()

        if (disposed) {
          return
        }

        await openPage(request)
      } catch (error) {
        if (!disposed) {
          onStatus(String(error))
          host.notify({ kind: 'error', message: `无法打开平台页面：${String(error)}` })
        }
      } finally {
        if ($loginNavigation.get() === request.id) {
          $loginNavigation.set(null)
          $loginNavigationOwner.set(null)
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
        $loginNavigationOwner.set(null)
      }

      if ($loginRequest.get()?.id === request.id) {
        $loginRequest.set(null)
      }
    }
  }, [openPage, owner, request, takeOver, onStatus])
}
