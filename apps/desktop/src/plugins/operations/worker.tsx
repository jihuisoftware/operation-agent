import { host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { executeBrowser } from './browser'
import { browserDockStyle, useBrowserDock } from './browser-dock'
import { BrowserToolbar } from './browser-toolbar'
import { createBrowserTrace } from './browser-trace'
import { createExecutionClock } from './execution-clock'
import { $loginNavigation, $loginNavigationOwner, sameLoginOwner } from './login-state'
import { PlatformLoginPage, PlatformPageFrame, PlatformPageTabs, usePlatformPages } from './platform-pages'
import { $showOperationsBrowser, beginBrowserActivity } from './state'
import type { Api, BrowserCommand } from './types'
import { useLoginObservation } from './use-login-observation'
import { useOperationsGuest } from './use-operations-guest'
import { usePlatformLogin } from './use-platform-login'
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
  const execution = useRef<{ pending: Promise<unknown> | null }>({ pending: null })
  const [worker] = useState(() => crypto.randomUUID())
  const manual = useRef(false)
  const commandScope = useRef<OperationScope | null>(null)
  const { guest, loading, error, reopen } = useOperationsGuest(scope, container)
  const pages = usePlatformPages(guest)

  useEffect(() => {
    const active = document.activeElement

    if (!visible && active instanceof HTMLElement && surface.current?.contains(active)) {
      active.blur()
    }
  }, [visible])

  const api = useMemo<Api>(
    () => (path, body, method) => {
      const selected = commandScope.current || (scope.business_id && scope.topic_id ? { business_id: scope.business_id, topic_id: scope.topic_id } : null)
      const polling = path === '/worker/poll' && scope.account_id

      return ctx.rest(polling ? '/workspaces/worker/poll' : selected ? scopePath(path, selected) : path, {
        owner: scope,
        method: method || (body ? 'POST' : 'GET'),
        body: polling ? { ...(body as object), account_id: scope.account_id } : body,
        timeoutMs: path === '/worker/verify-images' ? 60000 : 15000
      })
    },
    [ctx, scope]
  )

  // Login observations belong to the account's fixed scope, never an in-flight task's scope.
  const loginApi = useMemo<Api>(() => (path, body, method) => ctx.rest(
    scope.business_id && scope.topic_id ? scopePath(path, { business_id: scope.business_id, topic_id: scope.topic_id }) : path,
    { owner: scope, method: method || (body ? 'POST' : 'GET'), body, timeoutMs: 15000 }
  ), [ctx, scope])

  // Command scope is a server-issued request token, never a mirror of the selected UI scope.
  // eslint-disable-next-line no-restricted-syntax
  useEffect(() => {
    let disposed = false
    let running = false
    let polling = false
    let reportSeen = ''
    const noticeSeen = new Set<string | number>()
    let finishActivity: (() => void) | undefined

    const poll = async () => {
      if (disposed || polling || !guest.isConnected) {
        return
      }

      polling = true

      try {
        // Poll also heartbeats during a command; the server serializes the account across windows.
        const result = await api<{
          command: (BrowserCommand & { scope?: OperationScope; topic_name?: string }) | null
          latest_report?: ReportNotice
          publication_notices?: { id: number | string; platform: string; action_id: string; label?: string; scope?: OperationScope }[]
        }>('/worker/poll', { worker, busy: running || manual.current || loginBusy(scope) })

        reportSeen = reportNotice(result.latest_report, reportSeen, disposed, scope)

        publishNotices(result.publication_notices, noticeSeen, disposed, scope)

        if (!result.command || disposed || running) {
          return
        }

        polling = false
        running = true
        const endActivity = beginBrowserActivity(scope, result.command.kind)
        finishActivity = endActivity
        guest.style.pointerEvents = 'none'
        setStatus('正在执行任务；可点击人工接管暂停')

        try {
          const command = result.command
          commandScope.current = command.scope || null
          setTaskLabel(command.topic_name || '')
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
            setStatus(answer.error || '本次网页任务完成')
          }
        } finally {
          endActivity()
          running = false
          execution.current.pending = null
          commandScope.current = null
        }
      } catch (error) {
        if (!disposed) {
          setStatus(error instanceof Error ? error.message : '连接异常')
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
      setStatus('已暂停，等待当前网页操作退出…')
      await execution.current.pending?.then(
        () => undefined,
        error => setStatus(String(error))
      )
      guest.style.pointerEvents = 'auto'
      setStatus('网页已接管，采集与分析继续；完成后点击结束接管')
    } finally {
      manual.current = false
    }
  }, [api, guest, worker])

  usePlatformLogin({ openPage: pages.openPage, owner: scope, worker, takeOver, onStatus: setStatus })
  useLoginObservation({ api: loginApi, guest, worker, platform: 'xiaohongshu', onStatus: setStatus })

  const release = async () => { await loginApi('/worker/takeover', { worker, active: false }) }

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
              .then(() => setStatus('已结束接管，网页动作按后续排期执行；全局暂停保持原设置'))
              .catch(failed)
          }
          reopen={() => void takeOver().then(reopen).catch(failed)}
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
