import { host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { type ActiveBrowserExecution, runBrowserCommand } from './browser-command'
import { browserDockStyle, useBrowserDock } from './browser-dock'
import type { ExecutionBlock } from './browser-execution'
import { type BrowserPower, createBrowserPower } from './browser-power'
import { BACKEND_MS } from './browser-timeouts'
import { BrowserToolbar } from './browser-toolbar'
import { createExecutionClock } from './execution-clock'
import { $loginNavigation, $loginNavigationOwner, type LoginObservation, sameLoginOwner } from './login-state'
import { PlatformLoginPage, PlatformPageFrame, PlatformPageTabs, usePlatformPages } from './platform-pages'
import { $showOperationsBrowser, beginBrowserActivity } from './state'
import type { Api, BrowserCommand } from './types'
import { useLoginObservation } from './use-login-observation'
import { useOperationsGuest } from './use-operations-guest'
import { usePlatformLogin } from './use-platform-login'
import { useWebTakeover, type WebControlState } from './use-web-takeover'
import { AccountViewHeader } from './workspace-browser-header'
import { recordAction } from './workspace-notices'
import { $workspaceBrowser, $workspaces, loadWorkspaces, type OperationScope, ownerKey, scopePath } from './workspace-state'

interface WorkerOwner extends ReturnType<typeof host.state.requestOwner.get> {
  account_id?: string
  business_id?: string
  topic_id?: string
}

function loginBusy(owner: WorkerOwner) {
  const navigating = $loginNavigationOwner.get()

  return Boolean($loginNavigation.get() && navigating && sameLoginOwner(navigating, owner))
}

interface ReportNotice { id: string; day: string; label?: string; record_id?: string; scope?: OperationScope }

function reportNotice(report: ReportNotice | null | undefined, previous: string, disposed: boolean, owner: WorkerOwner) {
  if (disposed || !report || report.id === previous) { return previous }
  host.notify({ kind: 'info', message: `${report.label || ''} · ${report.day} 运营日报已生成，请到首页查看`, action: recordAction(owner, report.scope, `/overview?tab=reports&record=${encodeURIComponent(report.record_id || report.id)}`) })

  return report.id
}

function Worker({
  scope,
  ctx,
  visible
}: {
  scope: WorkerOwner
  ctx: PluginContext
  visible: boolean
}) {
  const [status, setStatus] = useState('等待连接')
  const [taskLabel, setTaskLabel] = useState('')
  const container = useRef<HTMLDivElement>(null)
  const surface = useRef<HTMLElement>(null)
  const execution = useRef<ActiveBrowserExecution>({ pending: null })
  const [worker] = useState(() => crypto.randomUUID())

  const powerControl = useRef<BrowserPower | null>(null)
  execution.current.worker = worker
  const { guest, loading, error, reopen, replace, back } = useOperationsGuest(scope, container)

  const pages = usePlatformPages(guest)

  useEffect(() => {
    const active = document.activeElement

    if (!visible && active instanceof HTMLElement && surface.current?.contains(active)) {
      active.blur()
    }
  }, [visible])

  const api = useMemo<Api>(
    () => (path, body, method) => {
      const selected = scope.business_id && scope.topic_id ? { business_id: scope.business_id, topic_id: scope.topic_id } : null
      const polling = path === '/worker/poll' && scope.account_id

      return ctx.rest(polling ? '/workspaces/worker/poll' : selected ? scopePath(path, selected) : path, {
        owner: scope,
        method: method || (body ? 'POST' : 'GET'),
        body: polling ? { ...(body as object), account_id: scope.account_id } : body,
        timeoutMs: path === '/worker/verify-images' ? 60000 : BACKEND_MS
      })
    },
    [ctx, scope]
  )

  // Login observations belong to the account's fixed scope, never an in-flight task's scope.
  const loginApi = useMemo<Api>(() => (path, body, method) => ctx.rest(
    scope.business_id && scope.topic_id ? scopePath(path, { business_id: scope.business_id, topic_id: scope.topic_id }) : path,
    { owner: scope, method: method || (body ? 'POST' : 'GET'), body, timeoutMs: 15000 }
  ), [ctx, scope])

  const { manual, revision: controlRevision, takeOver, release, reconcile } = useWebTakeover({ api: loginApi, guest, worker, execution, onStatus: setStatus })

  // Command scope is a server-issued request token, never a mirror of the selected UI scope.

  // The ref exposes this effect's controller to the retry button; it does not mirror reactive state.
  // eslint-disable-next-line no-restricted-syntax
  useEffect(() => {
    const executionState = execution.current
    let disposed = false
    let running = false
    let polling = false
    let reportSeen = ''
    const noticeSeen = new Set<string | number>()
    let finishActivity: (() => void) | undefined
    const powerApi: Api = (path, body, method) => ctx.rest(path, { owner: scope, method: method || (body ? 'POST' : 'GET'), body, timeoutMs: BACKEND_MS })
    const power = createBrowserPower({ ...scope, account_id: scope.account_id || 'local' }, powerApi, execution, setStatus, replace)
    powerControl.current = power

    const poll = async () => {
      if (disposed || polling || !guest.isConnected) {
        return
      }

      polling = true

      try {
        if (!await power.beforePoll(manual.current)) { return }
        const pollEpoch = power.epoch
        const observedControl = controlRevision.current

        // Poll also heartbeats during a command; the server serializes the account across windows.
        const result = await api<{
          command: (BrowserCommand & { scope?: OperationScope; topic_name?: string }) | null
          takeover?: WebControlState
          execution_block?: ExecutionBlock | null
          cancel_commands?: string[]
          latest_report?: ReportNotice
          publication_notices?: { id: number | string; platform: string; action_id: string; label?: string; scope?: OperationScope }[]
        }>('/worker/poll', { worker, busy: running || manual.current || loginBusy(scope), takeover: manual.current, ...(power.probeOnly ? { wake_only: true } : {}) })

        if (!disposed) {
          reconcile(result.takeover, observedControl)
          execution.current.context?.block(result.execution_block)
          execution.current.context?.cancel(result.cancel_commands)
          setStatus(previous => previous === '等待连接' ? '执行窗口已连接，等待任务' : previous)
        }

        reportSeen = reportNotice(result.latest_report, reportSeen, disposed, scope)

        publishNotices(result.publication_notices, noticeSeen, disposed, scope)

        if (!result.command || disposed || running) {
          return
        }

        if (!await power.admit(result.command, worker, pollEpoch)) { return }
        polling = false
        running = true
        const endActivity = beginBrowserActivity(scope, result.command.kind)
        finishActivity = endActivity
        guest.style.pointerEvents = 'none'
        setStatus('正在执行网页任务；慢网络加载最多等待 2 分钟，可人工接管中断')

        try {
          const command = result.command
          setTaskLabel(command.topic_name || '')

          const commandApi: Api = (path, body, method) => {
            const selected = command.scope || (scope.business_id && scope.topic_id ? { business_id: scope.business_id, topic_id: scope.topic_id } : null)

            return ctx.rest(selected ? scopePath(path, selected) : path, { owner: scope, method: method || (body ? 'POST' : 'GET'), body,
              timeoutMs: path === '/worker/verify-images' ? 60000 : BACKEND_MS })
          }

          const answer = await runBrowserCommand(command, guest, commandApi, worker, execution, clock.sleep, replace, () => !disposed, power)

          if (!disposed && !manual.current) {
            setStatus(answer.error || '本次网页任务完成')
          }
        } finally {
          endActivity()
          running = false
        }
      } catch (error) {
        if (!disposed) {
          setStatus(error instanceof Error ? error.message : '连接异常')
        }
      } finally {
        polling = false
      }
    }

    const unavailable = () => execution.current.context?.abort('网页进程已退出，请重新打开后手动继续', 'BROWSER_UNAVAILABLE')
    guest.addEventListener('render-process-gone', unavailable)
    const clock = createExecutionClock(() => void poll())
    void poll()

    return () => {
      disposed = true
      executionState.context?.abort('执行窗口已关闭或切换，停止旧任务', 'BROWSER_UNAVAILABLE')
      guest.removeEventListener('render-process-gone', unavailable)
      finishActivity?.()
      power.dispose()
      clock.dispose()
    }
  }, [scope, api, ctx, guest, worker, manual, controlRevision, reconcile, replace])

  usePlatformLogin({ openPage: pages.openPage, owner: scope, worker, takeOver, onStatus: setStatus })
  const observed = useCallback((observation: LoginObservation) => { execution.current.context?.observe(observation.state, observation.account_id) }, [])
  useLoginObservation({ api: loginApi, guest, worker, platform: 'xiaohongshu', onStatus: setStatus, onObservation: observed })


  const failed = (reason: unknown) => setStatus(String(reason))

  return (
    <section
      aria-hidden={!visible || undefined}
      aria-label="运营画面"
      className="flex flex-col overflow-hidden border-2 border-(--ui-stroke-secondary) bg-(--ui-surface-background) text-foreground"
      inert={!visible || undefined}
      ref={surface}
      style={browserDockStyle(visible)}
    >
      <AccountViewHeader scope={scope} taskLabel={taskLabel} />
      <PlatformPageTabs active={pages.active} opened={pages.opened} owner={scope} select={pages.select} />
      <PlatformPageFrame name="小红书" visible={visible && pages.active === 'xiaohongshu'}>
        <BrowserToolbar
          back={() => void takeOver().then(back).catch(failed)}
          error={error}

          hide={() => $showOperationsBrowser.set(false)}
          loading={loading}
          login={() =>
            void takeOver()
              .then(() => guest.loadURL('https://www.xiaohongshu.com'))
              .catch(failed)
          }
          release={() => void release().catch(failed)}
          reopen={() => void takeOver().then(reopen).catch(failed)}
          retryCheck={() => { powerControl.current?.retry(); setStatus('准备重新检查账号') }}
          status={status}
          takeOver={() => void takeOver().catch(failed)}
        />
        <div className="min-h-0 flex-1" ref={container} />
      </PlatformPageFrame>
      {pages.opened.filter(platform => platform !== 'xiaohongshu').map(platform => <PlatformLoginPage
        api={loginApi}
        key={platform}
        owner={scope}
        platform={platform}
        register={pages.register}
        release={release}
        takeOver={takeOver}
        visible={visible && pages.active === platform}
        worker={worker}
      />)}
    </section>
  )
}

export function OperationsWorker({ ctx }: { ctx: PluginContext }) {
  const active = useValue(host.state.requestOwner)
  const shown = useValue($showOperationsBrowser)
  const visible = useBrowserDock(shown)
  const [owners, setOwners] = useState([active])
  useEffect(() => { setOwners(previous => previous.some(o => ownerKey(o) === ownerKey(active)) ? previous : [...previous, active]) }, [active])

  return <>{owners.map(owner => <AccountWorkers ctx={ctx} key={ownerKey(owner)} owner={owner} visible={visible && ownerKey(owner) === ownerKey(active)} />)}</>
}

function AccountWorkers({ ctx, owner, visible }: { ctx: PluginContext; owner: ReturnType<typeof host.state.requestOwner.get>; visible: boolean }) {
  const state = useValue($workspaces)[ownerKey(owner)]
  const browser = useValue($workspaceBrowser)[ownerKey(owner)]
  useEffect(() => {
    void loadWorkspaces(ctx, owner)
    const timer = setInterval(() => void loadWorkspaces(ctx, owner), 15000)

    return () => clearInterval(timer)
  }, [ctx, owner])
  const accounts = state?.catalog?.accounts || []
  const selectedAccount = browser?.business_id === state?.selected?.business_id ? browser?.account_id : state?.catalog?.businesses.find(b => b.id === state.selected?.business_id)?.account

  return <>{accounts.map(account => {
    const business = state?.catalog?.businesses.find(b => b.account === account.id && !b.archived)
    const topic = state?.catalog?.topics.find(t => t.business_id === business?.id && !t.archived)

    return topic ? <OwnedAccountWorker accountId={account.id} businessId={topic.business_id} ctx={ctx} key={account.id} owner={owner} topicId={topic.id} visible={visible && account.id === selectedAccount} /> : null
  })}</>
}

function OwnedAccountWorker({ ctx, owner, accountId, businessId, topicId, visible }: {
  ctx: PluginContext; owner: ReturnType<typeof host.state.requestOwner.get>; accountId: string; businessId: string; topicId: string; visible: boolean
}) {
  const scope = useMemo(() => ({ ...owner, account_id: accountId, business_id: businessId, topic_id: topicId }), [owner, accountId, businessId, topicId])

  return <Worker ctx={ctx} scope={scope} visible={visible} />
}

function publishNotices(
  notices: { id: number | string; platform: string; action_id: string; label?: string; scope?: OperationScope }[] | undefined,
  seen: Set<number | string>,
  disposed: boolean,
  owner: WorkerOwner
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
      action: recordAction(owner, notice.scope, `/content?tab=published&record=${encodeURIComponent(notice.action_id)}`),
      message: `${notice.label || ''} · 发布审核${notice.platform === 'published' ? '已通过' : '未通过'}，请到内容页查看对应记录（${notice.action_id.slice(0, 8)}）`
    })
  }
}
