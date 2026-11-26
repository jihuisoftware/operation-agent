import { Button, host, type CronBlueprintOwner, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'

import { type BlueprintCatalog, moduleLabels } from './blueprint-types'
import { LibraryPage } from './library-page'
import { PlanEditor } from './plan-editor'
import { SharedModelBudget } from './shared-model-budget'
import { useOwnerContext } from './use-owner-context'
import { currentWorkspaceLink, guardWorkspaceChange, workspaceLink, WORKSPACES_PATH } from './workspace-navigation'
import { WorkspacePage } from './workspace-page'
import {
  $workspaces,
  loadWorkspaces,
  type OperationScope,
  ownerKey,
  scopedContext,
  type WorkspaceBusiness,
  type WorkspaceCatalog,
  type WorkspaceTopic
} from './workspace-state'
import { type SummaryRow, useWorkspaceSummary } from './workspace-summary'

type Manage = (body: Record<string, unknown>) => Promise<void>

export function WorkspaceManagement({ ctx }: { ctx: PluginContext }) {
  const owner = useValue(host.state.requestOwner)
  const [params] = useSearchParams()
  if (params.get('view') === 'plan') {
    return (
      <WorkspacePage ctx={ctx} owner={owner}>
        {scoped => <TopicPlan ctx={scoped} owner={owner} />}
      </WorkspacePage>
    )
  }
  return <Directory ctx={ctx} key={ownerKey(owner)} owner={owner} />
}

function TopicPlan({ ctx, owner }: { ctx: PluginContext; owner: CronBlueprintOwner }) {
  const state = useValue($workspaces)[ownerKey(owner)]
  const topic = state?.catalog?.topics.find(t => t.id === state.selected?.topic_id)
  const business = state?.catalog?.businesses.find(b => b.id === state.selected?.business_id)
  return (
    <section className="p-4">
      <Button onClick={() => guardWorkspaceChange(owner, () => host.navigate(WORKSPACES_PATH))} variant="link">
        返回业务与主题
      </Button>
      {topic?.archived || business?.archived ? (
        <ArchivedPlan ctx={ctx} owner={owner} />
      ) : (
        <PlanEditor ctx={ctx} owner={owner} />
      )}
    </section>
  )
}

export function TopicPlanLink() {
  return (
    <Button onClick={() => host.navigate(currentWorkspaceLink('plan'))} size="sm" variant="link">
      查看所属运营计划
    </Button>
  )
}

export function ExecutionPlanLink({ owner, context }: { owner: CronBlueprintOwner; context: Record<string, unknown> }) {
  const active = useValue(host.state.requestOwner)
  if (ownerKey(active) !== ownerKey(owner)) return null
  const { business_id, topic_id } = context
  if (typeof business_id !== 'string' || !business_id || typeof topic_id !== 'string' || !topic_id) return null
  return (
    <Button onClick={() => host.navigate(workspaceLink('plan', { business_id, topic_id }))} size="sm" variant="link">
      查看执行记录所属计划{typeof context.topic === 'string' && context.topic ? ' · ' + context.topic : ''}
    </Button>
  )
}

export function TopicHistory({ ctx }: { ctx: PluginContext }) {
  const owner = useValue(host.state.requestOwner)
  const state = useValue($workspaces)[ownerKey(owner)]
  const archived =
    state?.catalog?.topics.some(t => t.id === state.selected?.topic_id && t.archived) ||
    state?.catalog?.businesses.some(b => b.id === state.selected?.business_id && b.archived)
  return (
    <>
      <TopicPlanLink />
      <h2 className="px-4 font-medium">运营台账与临时任务</h2>
      <LibraryPage ctx={ctx} readOnly={archived} section="history" />
    </>
  )
}

function ArchivedPlan({ ctx, owner }: { ctx: PluginContext; owner: CronBlueprintOwner }) {
  const [plan, setPlan] = useState<BlueprintCatalog | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let live = true
    void ctx.rest<BlueprintCatalog>('/blueprints').then(
      result => {
        if (live) setPlan(result)
      },
      reason => {
        if (live) setError(String(reason))
      }
    )
    return () => {
      live = false
    }
  }, [ctx])
  const scope = useValue($workspaces)[ownerKey(owner)]?.selected
  return (
    <section className="space-y-3 p-4">
      <h2>已归档主题 · 只读</h2>
      {error && <p role="alert">{error}</p>}
      {plan && (
        <>
          <p>{plan.policy.goal || '尚未设置目标'}</p>
          <p>
            运营场景 ·{' '}
            {plan.templates.find(t => t.id === plan.policy.business_theme)?.title ||
              plan.policy.business_subtype ||
              '自定义'}
          </p>
          <ul>
            {Object.keys(plan.policy.modules)
              .filter(key => plan.policy.modules[key])
              .map(key => (
                <li key={key}>
                  {moduleLabels[key] || key} · {plan.policy.times[key]?.join('、') || '未设置时间'}
                </li>
              ))}
          </ul>
        </>
      )}
      <Button onClick={() => host.navigate(workspaceLink('history', scope))}>查看运营历史</Button>
    </section>
  )
}

function Directory({ ctx, owner }: { ctx: PluginContext; owner: CronBlueprintOwner }) {
  const state = useValue($workspaces)[ownerKey(owner)]
  const bound = useOwnerContext(ctx, owner)
  const [query, setQuery] = useState('')
  const [archived, setArchived] = useState(false)
  const [busy, setBusy] = useState(false)
  const mounted = useRef(false)
  const saving = useRef(false)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])
  useEffect(() => {
    void loadWorkspaces(ctx, owner)
  }, [ctx, owner])
  const catalog = state?.catalog
  const { rows, error } = useWorkspaceSummary(bound, catalog)
  const open = (scope: OperationScope) => guardWorkspaceChange(owner, () => host.navigate(workspaceLink('plan', scope)))
  const manage: Manage = async body => {
    if (saving.current) return
    saving.current = true
    setBusy(true)
    try {
      const result = await bound.rest<OperationScope | WorkspaceCatalog>('/workspaces', { method: 'POST', body })
      if (ownerKey(host.state.requestOwner.get()) !== ownerKey(owner)) return
      await loadWorkspaces(ctx, owner)
      if (mounted.current && 'topic_id' in result && ownerKey(host.state.requestOwner.get()) === ownerKey(owner))
        open(result)
    } finally {
      saving.current = false
      if (mounted.current) setBusy(false)
    }
  }
  const [params] = useSearchParams()
  const writable = catalog?.topics.find(
    t => !t.archived && !catalog.businesses.find(b => b.id === t.business_id)?.archived
  )
  const budget = useMemo(
    () => writable && scopedContext(ctx, owner, { business_id: writable.business_id, topic_id: writable.id }),
    [ctx, owner, writable]
  )
  if (!catalog)
    return (
      <p role="status">
        {state?.error || '正在读取业务与主题…'}
        {state?.error && <Button onClick={() => void loadWorkspaces(ctx, owner)}>重试</Button>}
      </p>
    )
  return (
    <main aria-label="业务与主题" className="h-full space-y-4 overflow-auto p-5">
      <h1 className="text-xl font-semibold">业务与主题</h1>
      <input
        aria-label="搜索业务或主题"
        className="rounded border bg-background p-2"
        onChange={e => setQuery(e.target.value)}
        placeholder="搜索业务或主题"
        value={query}
      />
      <label className="ml-3">
        <input checked={archived} onChange={e => setArchived(e.target.checked)} type="checkbox" /> 查看已归档
      </label>
      {(error || state.error) && <p role="alert">{error || state.error}</p>}
      <fieldset className="space-y-3" disabled={busy}>
        <WorkspaceAction body={{ action: 'create' }} manage={manage} owner={owner} title="新建业务" />
        {catalog.businesses
          .filter(b => archived || !b.archived)
          .map(b => (
            <BusinessGroup
              key={b.id}
              business={b}
              catalog={catalog}
              owner={owner}
              manage={manage}
              query={query.trim().toLocaleLowerCase()}
              archived={archived}
              summaries={rows}
              selected={state.selected}
              openPlan={open}
            />
          ))}
        <details open={params.get('view') === 'settings' || undefined}>
          <summary>全部业务设置</summary>
          <WorkspaceAction
            body={{ action: catalog.paused ? 'resume' : 'pause', kind: 'profile' }}
            impact="此操作影响当前 Profile 下全部业务。"
            manage={manage}
            owner={owner}
            title={catalog.paused ? '恢复全部运营' : '暂停全部运营'}
          />
          {budget && <SharedModelBudget ctx={budget} />}
        </details>
      </fieldset>
    </main>
  )
}

interface BusinessGroupProps {
  business: WorkspaceBusiness
  catalog: WorkspaceCatalog
  manage: Manage
  owner: CronBlueprintOwner
  archived: boolean
  query: string
  summaries: SummaryRow[]
  selected?: OperationScope
  openPlan: (scope: OperationScope) => void
}

function BusinessGroup({
  business,
  catalog,
  owner,
  manage,
  archived,
  query,
  summaries,
  selected,
  openPlan
}: BusinessGroupProps) {
  const matchesBusiness = business.name.toLocaleLowerCase().includes(query)
  const topics = catalog.topics.filter(
    t =>
      t.business_id === business.id &&
      (archived || !t.archived) &&
      (matchesBusiness || t.name.toLocaleLowerCase().includes(query))
  )
  if (!matchesBusiness && !topics.length) return null
  return (
    <details className="space-y-2 rounded border p-3" open>
      <summary className="cursor-pointer">
        <h2 className="inline font-medium">
          {business.name}
          {business.archived ? '（已归档）' : business.paused ? '（已暂停）' : ''}
        </h2>
      </summary>
      {!business.archived && <BusinessActions business={business} catalog={catalog} manage={manage} owner={owner} />}
      {topics.map(t => (
        <TopicRow
          key={t.id}
          topic={t}
          business={business}
          owner={owner}
          manage={manage}
          selected={selected?.topic_id === t.id}
          summary={summaries.find(row => row.id === t.id)}
          openPlan={openPlan}
        />
      ))}
    </details>
  )
}

function topicStatus(summary?: SummaryRow) {
  if (!summary) return ''
  if (summary.running.length) return '执行中'
  if (summary.paused) return '已暂停'
  if (summary.enabled) return '已启用'
  return summary.version ? '已保存' : '待配置'
}

interface TopicRowProps extends Pick<BusinessGroupProps, 'business' | 'manage' | 'owner' | 'openPlan'> {
  topic: WorkspaceTopic
  selected: boolean
  summary?: SummaryRow
}

function TopicRow({ topic, business, owner, manage, selected, summary, openPlan }: TopicRowProps) {
  const readonly = !!(topic.archived || business.archived)
  return (
    <div className="flex flex-wrap items-center gap-2 border-t py-2">
      <span>{topic.name}</span>
      {selected && <strong>当前主题</strong>}
      <span>{readonly ? '已归档' : topicStatus(summary)}</span>
      <Button onClick={() => openPlan({ business_id: business.id, topic_id: topic.id })} size="sm">
        {readonly ? '查看只读详情' : '打开运营计划'}
      </Button>
      {!readonly && (
        <details>
          <summary>主题管理</summary>
          <WorkspaceAction
            body={{ action: 'create', business_id: business.id, copy_topic: topic.id }}
            manage={manage}
            owner={owner}
            title="复制配置为新主题"
          />
          <WorkspaceAction
            body={{ action: 'create', copy_topic: topic.id }}
            manage={manage}
            owner={owner}
            title="复制配置为新业务"
          />
          <WorkspaceAction
            body={{ action: 'archive', kind: 'topics', id: topic.id }}
            impact={`归档「${business.name} / ${topic.name}」后保留只读历史。`}
            manage={manage}
            owner={owner}
            title="归档主题"
          />
        </details>
      )}
    </div>
  )
}

function BusinessActions({
  business: b,
  catalog,
  manage,
  owner
}: {
  business: WorkspaceBusiness
  catalog: WorkspaceCatalog
  manage: Manage
  owner: CronBlueprintOwner
}) {
  const [account, setAccount] = useState(b.account)
  useEffect(() => setAccount(b.account), [b.account])
  return (
    <details>
      <summary>管理「{b.name}」</summary>
      <div className="space-y-2">
        <WorkspaceAction
          body={{ action: 'create', business_id: b.id }}
          manage={manage}
          owner={owner}
          title="新建独立主题"
        />
        <WorkspaceAction
          body={{ action: 'rename', kind: 'businesses', id: b.id }}
          manage={manage}
          owner={owner}
          title="重命名业务"
        />
        <WorkspaceAction
          body={{ action: b.paused ? 'resume' : 'pause', kind: 'businesses', id: b.id }}
          impact={`影响「${b.name}」下所有主题。`}
          manage={manage}
          owner={owner}
          title={b.paused ? '恢复业务' : '暂停业务'}
        />
        <WorkspaceAction
          body={{ action: 'archive', kind: 'businesses', id: b.id }}
          impact={`「${b.name}」及其全部主题将归档，历史保留只读。`}
          manage={manage}
          owner={owner}
          title="归档业务"
        />
        <label>
          关联账号{' '}
          <select value={account} onChange={e => setAccount(e.target.value)}>
            {catalog.accounts.map(a => (
              <option key={a.id} value={a.id}>
                {a.identity || '独立登录 ' + a.id.slice(0, 8)}
                {a.conflict ? '（重复账号）' : ''}
              </option>
            ))}
          </select>
        </label>
        {account !== b.account && (
          <WorkspaceAction
            body={{ action: 'link_account', business_id: b.id, account_id: account }}
            impact="同账号业务共享登录、额度和网页队列，各主题保留独立资料。"
            manage={manage}
            owner={owner}
            title="更换关联账号"
          />
        )}
      </div>
    </details>
  )
}

function WorkspaceAction({
  title,
  impact,
  body,
  manage,
  owner
}: {
  title: string
  impact?: string
  body: Record<string, string>
  manage: Manage
  owner: CronBlueprintOwner
}) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const submit = () =>
    guardWorkspaceChange(owner, () => {
      setError('')
      void manage(impact ? body : { ...body, name: name.trim() }).then(
        () => {
          setOpen(false)
          setName('')
        },
        reason => setError(String(reason))
      )
    })
  if (!open)
    return (
      <Button onClick={() => setOpen(true)} size="sm" variant="outline">
        {title}
      </Button>
    )
  return (
    <div className="space-x-2 py-1">
      {impact ? (
        <span>{impact}</span>
      ) : (
        <label>
          {title}名称{' '}
          <input
            className="rounded border bg-background px-2 py-1"
            maxLength={120}
            onChange={e => setName(e.target.value)}
            value={name}
          />
        </label>
      )}
      <Button disabled={!impact && !name.trim()} onClick={submit} size="sm">
        确认{title}
      </Button>
      <Button onClick={() => setOpen(false)} size="sm" variant="ghost">
        取消
      </Button>
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
