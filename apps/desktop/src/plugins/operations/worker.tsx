import { host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { executeBrowser } from './browser'
import { $loginNavigation } from './login-state'
import { $operationsWorkerStatus, $showOperationsBrowser } from './state'
import type { Api, BrowserCommand, Guest, OperationsState } from './types'
import { usePlatformLogin } from './use-platform-login'

function Worker({ scope, ctx }: { scope: ReturnType<typeof host.state.requestOwner.get>; ctx: PluginContext }) {
  const visible = useValue($showOperationsBrowser)
  const status = useValue($operationsWorkerStatus)
  const container = useRef<HTMLDivElement>(null)
  const execution = useRef<{ pending: Promise<unknown> | null }>({ pending: null })
  const [worker] = useState(() => crypto.randomUUID())
  const manual = useRef(false)
  const [guest] = useState(() => document.createElement('webview') as Guest)

  const api = useMemo<Api>(
    () => (path, body, method) =>
      ctx.rest(path, {
        owner: scope,
        method: method || (body ? 'POST' : 'GET'),
        body,
        timeoutMs: 15000
      }),
    [ctx, scope]
  )

  useEffect(() => {
    let disposed = false
    let running = false
    let polling = false
    let reportSeen = ''
    let timer: ReturnType<typeof setInterval>
    guest.setAttribute('webpreferences', 'contextIsolation=yes,sandbox=yes,nodeIntegration=no,backgroundThrottling=no')
    guest.style.cssText = 'width:100%;height:100%;display:flex'
    // Separate cookie jar for each connection/profile; no guest preload or OS-browser popup bridge.
    void crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(scope))).then(buffer => {
      if (disposed) {
        return
      }

      const key = Array.from(new Uint8Array(buffer), byte => byte.toString(16).padStart(2, '0')).join('')
      guest.setAttribute('partition', `persist:operations-${key}`)
      guest.setAttribute('src', 'about:blank')
      container.current?.append(guest)
    })

    const poll = async () => {
      if (disposed || polling || !guest.isConnected) {
        return
      }

      polling = true

      try {
        // Poll also heartbeats during a command; the server serializes the account across windows.
        const result = await api<{ command: BrowserCommand | null; latest_report?: { id: string; day: string } }>(
          '/worker/poll',
          { worker, busy: running || manual.current || $loginNavigation.get() !== null }
        )

        if (!disposed && result.latest_report && result.latest_report.id !== reportSeen) {
          reportSeen = result.latest_report.id
          host.notify({
            kind: 'info',
            message: `${result.latest_report.day} 运营日报已生成，请到自动运营 → 每日总结查看`
          })
        }

        if (!result.command || disposed || running) {
          return
        }

        polling = false
        running = true
        guest.style.pointerEvents = 'none'
        $operationsWorkerStatus.set('正在执行任务；可点击人工接管暂停')

        try {
          const pending = manual.current
            ? Promise.resolve({ state: 'blocked', error: '已进入人工接管' })
            : executeBrowser(result.command, guest, api)

          execution.current.pending = pending
          const answer = await pending

          if (!disposed) {
            await api('/worker/ack', { id: result.command.id, worker, result: answer })
          }

          if (!disposed) {
            $operationsWorkerStatus.set(answer.error || '本次网页任务完成')
          }
        } finally {
          running = false
          execution.current.pending = null
        }
      } catch (error) {
        if (!disposed) {
          $operationsWorkerStatus.set(error instanceof Error ? error.message : '连接异常')
        }
      } finally {
        polling = false
      }
    }

    timer = setInterval(() => void poll(), 2000)
    void poll()

    return () => {
      disposed = true
      clearInterval(timer)
      guest.remove()
    }
  }, [scope, api, guest, worker])

  const takeOver = useCallback(async () => {
    manual.current = true

    try {
      const current = await api<OperationsState>('/policy')
      await api('/policy', { version: current.version, policy: { ...current.policy, paused: true } }, 'PUT')
      $operationsWorkerStatus.set('已暂停，等待当前网页操作退出…')
      await execution.current.pending?.then(
        () => undefined,
        error => $operationsWorkerStatus.set(String(error))
      )
      guest.style.pointerEvents = 'auto'
      $operationsWorkerStatus.set('已暂停自动动作，可人工操作网页；恢复请回运营工作台')
    } finally {
      manual.current = false
    }
  }, [api, guest])

  usePlatformLogin({ api, guest, owner: scope, worker, takeOver })

  return (
    <section
      style={{
        position: 'fixed',
        top: visible ? 55 : -10000,
        right: 8,
        width: visible ? '55vw' : 1000,
        height: visible ? 'calc(100vh - 65px)' : 800,
        zIndex: 90,
        background: 'var(--background)',
        border: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column'
      }}
    >
      <div className="flex flex-wrap items-center gap-2 border-b p-2 text-xs">
        <strong>自动运营实时画面</strong>
        <button onClick={() => void takeOver().catch(error => $operationsWorkerStatus.set(String(error)))}>
          暂停并人工接管
        </button>
        <button
          onClick={() =>
            void takeOver()
              .then(() => guest?.loadURL('https://www.xiaohongshu.com'))
              .catch(error => $operationsWorkerStatus.set(String(error)))
          }
        >
          打开小红书／登录
        </button>
        <button onClick={() => $showOperationsBrowser.set(false)}>隐藏画面</button>
        <span>{status}</span>
      </div>
      <div className="min-h-0 flex-1" ref={container} />
    </section>
  )
}

export function OperationsWorker({ ctx }: { ctx: PluginContext }) {
  const scope = useValue(host.state.requestOwner)

  return <Worker ctx={ctx} key={JSON.stringify(scope)} scope={scope} />
}
