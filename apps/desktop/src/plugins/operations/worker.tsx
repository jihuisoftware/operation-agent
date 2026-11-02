import { host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { executeBrowser } from './browser'
import { browserDockStyle, useBrowserDock } from './browser-dock'
import { BrowserToolbar } from './browser-toolbar'
import { createBrowserTrace } from './browser-trace'
import { createExecutionClock } from './execution-clock'
import { $loginNavigation } from './login-state'
import { $operationsWorkerStatus, $showOperationsBrowser, beginBrowserActivity } from './state'
import type { Api, BrowserCommand } from './types'
import { useOperationsGuest } from './use-operations-guest'
import { usePlatformLogin } from './use-platform-login'

function Worker({
  scope,
  ctx,
  visible
}: {
  scope: ReturnType<typeof host.state.requestOwner.get>
  ctx: PluginContext
  visible: boolean
}) {
  const status = useValue($operationsWorkerStatus)
  const container = useRef<HTMLDivElement>(null)
  const surface = useRef<HTMLElement>(null)
  const execution = useRef<{ pending: Promise<unknown> | null }>({ pending: null })
  const [worker] = useState(() => crypto.randomUUID())
  const manual = useRef(false)
  const { guest, loading, error, reopen } = useOperationsGuest(scope, container)

  useEffect(() => {
    const active = document.activeElement

    if (!visible && active instanceof HTMLElement && surface.current?.contains(active)) {
      active.blur()
    }
  }, [visible])

  const api = useMemo<Api>(
    () => (path, body, method) =>
      ctx.rest(path, {
        owner: scope,
        method: method || (body ? 'POST' : 'GET'),
        body,
        timeoutMs: path === '/worker/verify-images' ? 60000 : 15000
      }),
    [ctx, scope]
  )

  useEffect(() => {
    let disposed = false
    let running = false
    let polling = false
    let reportSeen = ''
    const noticeSeen = new Set<number>()
    let finishActivity: (() => void) | undefined

    const poll = async () => {
      if (disposed || polling || !guest.isConnected) {
        return
      }

      polling = true

      try {
        // Poll also heartbeats during a command; the server serializes the account across windows.
        const result = await api<{
          command: BrowserCommand | null
          latest_report?: { id: string; day: string }
          publication_notices?: { id: number; platform: string; action_id: string }[]
        }>('/worker/poll', { worker, busy: running || manual.current || $loginNavigation.get() !== null })

        if (!disposed && result.latest_report && result.latest_report.id !== reportSeen) {
          reportSeen = result.latest_report.id
          host.notify({
            kind: 'info',
            message: `${result.latest_report.day} 运营日报已生成，请到自动运营 → 每日总结查看`
          })
        }

        publishNotices(result.publication_notices, noticeSeen, disposed)

        if (!result.command || disposed || running) {
          return
        }

        polling = false
        running = true
        const endActivity = beginBrowserActivity(scope, result.command.kind)
        finishActivity = endActivity
        guest.style.pointerEvents = 'none'
        $operationsWorkerStatus.set('正在执行任务；可点击人工接管暂停')

        try {
          const command = result.command
          const trace = createBrowserTrace(command, guest, api, worker)

          const pending = manual.current
            ? Promise.resolve({ state: 'blocked', error: '已进入人工接管' })
            : trace.step('execution', () => executeBrowser(command, guest, api, clock.sleep, trace, worker))

          execution.current.pending = pending
          const answer = await pending

          if (!disposed) {
            await api('/worker/ack', { id: result.command.id, worker, result: answer })
          }

          if (!disposed) {
            $operationsWorkerStatus.set(answer.error || '本次网页任务完成')
          }
        } finally {
          endActivity()
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

    const clock = createExecutionClock(() => void poll())
    void poll()

    return () => {
      disposed = true
      finishActivity?.()
      clock.dispose()
    }
  }, [scope, api, guest, worker])

  const takeOver = useCallback(async () => {
    manual.current = true

    try {
      await api('/worker/takeover', { worker, active: true })
      $operationsWorkerStatus.set('已暂停，等待当前网页操作退出…')
      await execution.current.pending?.then(
        () => undefined,
        error => $operationsWorkerStatus.set(String(error))
      )
      guest.style.pointerEvents = 'auto'
      $operationsWorkerStatus.set('网页已接管，采集与分析继续；完成后点击结束接管')
    } finally {
      manual.current = false
    }
  }, [api, guest, worker])

  usePlatformLogin({ api, guest, owner: scope, worker, takeOver })

  const failed = (reason: unknown) => $operationsWorkerStatus.set(String(reason))

  return (
    <section
      aria-hidden={!visible || undefined}
      aria-label="运营画面"
      className="flex flex-col overflow-hidden border-2 border-(--ui-stroke-secondary) bg-(--ui-surface-background) text-foreground"
      inert={!visible || undefined}
      ref={surface}
      style={browserDockStyle(visible)}
    >
      <BrowserToolbar
        error={error}
        hide={() => $showOperationsBrowser.set(false)}
        loading={loading}
        login={() =>
          void takeOver()
            .then(() => guest.loadURL('https://www.xiaohongshu.com'))
            .catch(failed)
        }
        release={() =>
          void api('/worker/takeover', { worker, active: false })
            .then(() => $operationsWorkerStatus.set('已结束接管，网页动作按后续排期执行；全局暂停保持原设置'))
            .catch(failed)
        }
        reopen={() => void takeOver().then(reopen).catch(failed)}
        status={status}
        takeOver={() => void takeOver().catch(failed)}
      />
      <div className="min-h-0 flex-1" ref={container} />
    </section>
  )
}

export function OperationsWorker({ ctx }: { ctx: PluginContext }) {
  const active = useValue(host.state.requestOwner)
  const shown = useValue($showOperationsBrowser)
  const visible = useBrowserDock(shown)

  const scope = useMemo(
    () => ({ profile: active.profile, connectionId: active.connectionId }),
    [active.profile, active.connectionId]
  )

  return <Worker ctx={ctx} key={JSON.stringify(scope)} scope={scope} visible={visible} />
}

function publishNotices(
  notices: { id: number; platform: string; action_id: string }[] | undefined,
  seen: Set<number>,
  disposed: boolean
) {
  if (disposed) {
    return
  }

  for (const notice of notices || []) {
    if (seen.has(notice.id)) {
      continue
    }

    seen.add(notice.id)
    host.notify({
      kind: 'info',
      message: `发布审核${notice.platform === 'published' ? '已通过' : '未通过'}，请到运营管理查看对应记录（${notice.action_id.slice(0, 8)}）`
    })
  }
}
