import {
  Badge,
  Button,
  type CronBlueprintOwner,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  host,
  type PluginContext,
  RowButton,
  SegmentedControl,
  useValue
} from '@hermes/plugin-sdk'
import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'

import { type BlueprintCatalog, type BlueprintTemplate, moduleLabels } from './blueprint-types'
import { BlueprintWizard } from './blueprint-wizard'
import { $showOperationsBrowser } from './state'
import type { Policy } from './types'
import { Workbench } from './workbench'

interface LibraryProps {
  ctx: PluginContext
  owner: CronBlueprintOwner
  view: 'blueprints' | 'summary'
}

export function BlueprintLibrary({ ctx, owner, view }: LibraryProps) {
  const scoped = useMemo<PluginContext>(
    () => ({ ...ctx, rest: (path, options) => ctx.rest(path, { ...options, owner }) }),
    [ctx, owner]
  )

  return <OwnedLibrary ctx={scoped} key={JSON.stringify(owner)} owner={owner} view={view} />
}

function OwnedLibrary({ ctx, owner, view }: LibraryProps) {
  const [catalog, setCatalog] = useState<BlueprintCatalog | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [selected, setSelected] = useState('daily')
  const [category, setCategory] = useState('全部')
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Policy | undefined>()
  const [resource, setResource] = useState<string | null>(null)
  const activeOwner = useValue(host.state.requestOwner)

  const canView =
    activeOwner.connectionId === owner.connectionId &&
    (activeOwner.profile || 'default') === (owner.profile || 'default')

  const refresh = useCallback(async () => {
    const result = await ctx.rest<BlueprintCatalog>('/blueprints')
    setCatalog(result)
    setError('')
  }, [ctx])

  useEffect(() => {
    let disposed = false

    const update = async () => {
      try {
        const result = await ctx.rest<BlueprintCatalog>('/blueprints')

        if (!disposed) {
          setCatalog(result)
          setError('')
        }
      } catch (error) {
        if (!disposed) {
          setError(String(error))
        }
      }
    }

    void update()
    const timer = setInterval(() => void update(), 5000)

    return () => {
      disposed = true
      clearInterval(timer)
    }
  }, [ctx])

  const applySaved = async () => {
    await refresh()
    setEditing(false)
    setDraft(undefined)
    setNotice('已保存。任务与工作台使用同一份运营规则。')
  }

  const choose = (template: BlueprintTemplate) => {
    setSelected(template.id)
    setEditing(false)
    setDraft(undefined)
    setNotice('')
  }

  const resources = (
    <div className="flex flex-wrap gap-2">
      {['素材与内容', '任务与执行', '来源与数据', '每日总结'].map(label => (
        <Button key={label} onClick={() => setResource(label)} size="sm" variant="ghost">
          {label}
        </Button>
      ))}
      <Button
        disabled={!canView}
        onClick={() => $showOperationsBrowser.set(true)}
        size="sm"
        title={canView ? '查看当前账号的执行网页' : '请先切换到此 Profile 再查看网页'}
        variant="ghost"
      >
        实时画面
      </Button>
    </div>
  )

  if (!catalog) {
    return (
      <div className="space-y-3 p-5 text-sm">
        <p role="status">{error ? `运营服务不可用：${error}` : '正在加载运营蓝图…'}</p>
        {error && (
          <>
            <p>请确认 Server 已更新且运营插件可用，不会使用普通提示词任务替代执行。</p>
            <Button onClick={() => void refresh().catch(error => setError(String(error)))} variant="outline">
              重新连接
            </Button>
          </>
        )}
      </div>
    )
  }

  const template = catalog.templates.find(t => t.id === selected) || catalog.templates[0]
  const businesses = catalog.templates.filter(t => t.kind === 'business')
  const scenarios = catalog.templates.filter(t => t.kind === 'scenario')
  const modules = catalog.templates.filter(t => t.id !== 'daily' && !t.kind)
  const categories = ['全部', ...new Set(modules.map(t => t.category))]

  return (
    <div className="space-y-4 p-4 text-sm">
      <PlanHeader catalog={catalog} owner={owner}>
        {resources}
      </PlanHeader>
      {error && (
        <p className="text-destructive" role="alert">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {view === 'blueprints' && (
        <>
          <div className="space-y-2">
            <h2 className="text-lg font-semibold">按场景选择定时任务</h2>
            <p className="text-muted-foreground">
              先选业务主题或执行场景，调整定位、任务和时间，再保存草稿或应用启用。已有计划的时间、权限和额度会保留。
            </p>
          </div>
          {catalog.draft && (
            <div className="flex flex-wrap items-center gap-2">
              <span>有一份未应用的蓝图草稿。</span>
              <Button
                disabled={catalog.draft.version !== catalog.version}
                onClick={() => {
                  setSelected('daily')
                  setDraft(catalog.draft!.policy)
                  setEditing(true)
                }}
                size="sm"
                variant="outline"
              >
                继续配置
              </Button>
              {catalog.draft.version !== catalog.version && (
                <span className="text-muted-foreground">现有规则已变化，请重新配置，避免覆盖。</span>
              )}
            </div>
          )}
          <div className="grid gap-6 lg:grid-cols-[minmax(230px,2fr)_minmax(320px,3fr)]">
            <div className="space-y-4">
              {businesses.length > 0 && (
                <section aria-label="业务主题" className="space-y-2">
                  <h3 className="font-medium">按业务选择默认配置</h3>
                  {businesses.map(t => (
                    <TemplateRow key={t.id} onSelect={() => choose(t)} selected={t.id === selected} template={t} />
                  ))}
                </section>
              )}
              <TemplateRow
                onSelect={() => choose(catalog.templates[0])}
                selected={selected === 'daily'}
                template={catalog.templates[0]}
              />
              {scenarios.length > 0 && (
                <section aria-label="推荐场景" className="space-y-2">
                  <h3 className="font-medium">推荐场景</h3>
                  {scenarios.map(t => (
                    <TemplateRow key={t.id} onSelect={() => choose(t)} selected={t.id === selected} template={t} />
                  ))}
                </section>
              )}
              <h3 className="font-medium">按模块自定义</h3>
              <div className="overflow-x-auto">
                <SegmentedControl
                  onChange={setCategory}
                  options={categories.map(id => ({ id, label: id }))}
                  sizing="content"
                  value={category}
                />
              </div>
              <div>
                {modules
                  .filter(t => category === '全部' || t.category === category)
                  .map(t => (
                    <TemplateRow key={t.id} onSelect={() => choose(t)} selected={t.id === selected} template={t} />
                  ))}
              </div>
            </div>
            <section aria-label="蓝图配置" className="min-w-0 space-y-4">
              {editing ? (
                <BlueprintWizard
                  catalog={catalog}
                  ctx={ctx}
                  draft={draft}
                  key={`${selected}:${draft ? 'draft' : 'new'}`}
                  onAssets={() => setResource('素材与内容')}
                  onSaved={applySaved}
                  template={template}
                />
              ) : (
                <TemplateDetail onConfigure={() => setEditing(true)} template={template} />
              )}
            </section>
          </div>
        </>
      )}
      <Dialog
        onOpenChange={open => {
          if (!open) {
            setResource(null)
            void refresh().catch(error => setError(String(error)))
          }
        }}
        open={resource !== null}
      >
        <DialogContent className="max-h-[85vh] overflow-auto sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle>{resource}</DialogTitle>
          </DialogHeader>
          {resource && <Workbench ctx={ctx} initialTab={resource} owner={owner} />}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function TemplateRow({
  template,
  selected,
  onSelect
}: {
  template: BlueprintTemplate
  selected: boolean
  onSelect: () => void
}) {
  return (
    <RowButton
      aria-pressed={selected}
      className={`w-full space-y-2 rounded-md p-3 text-left transition-colors hover:bg-accent ${selected ? 'bg-accent' : ''}`}
      onClick={onSelect}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">{template.title}</span>
        <Badge variant="muted">{template.status}</Badge>
      </div>
      <p className="text-xs text-muted-foreground">{template.output}</p>
      <p className="text-xs text-muted-foreground">
        {template.id === 'daily'
          ? '推荐 · 按需组合每日流程'
          : [...new Set(Object.values(template.times).flat())].join('、')}
      </p>
    </RowButton>
  )
}

function PlanHeader({
  catalog,
  owner,
  children
}: {
  catalog: BlueprintCatalog
  owner: CronBlueprintOwner
  children: ReactNode
}) {
  const business = catalog.templates.find(t => t.kind === 'business' && t.id === catalog.policy.business_theme)

  const state = !catalog.policy.enabled
    ? '未启用'
    : catalog.policy.paused
      ? '已暂停'
      : catalog.schedule_state === 'ready'
        ? '运行中'
        : '调度待恢复'

  return (
    <header className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-semibold">{catalog.policy.topic || '先为运营计划设置主题'}</h2>
        <Badge variant="muted">{state}</Badge>
        {business && (
          <Badge variant="muted">
            {business.title}
            {catalog.policy.business_subtype ? ` · ${catalog.policy.business_subtype}` : ''}
          </Badge>
        )}
        <span className="text-xs text-muted-foreground">
          配置：{owner.profile || 'default'} · {catalog.online ? '桌面执行器在线' : '桌面执行器离线'}
        </span>
      </div>
      <p className="text-muted-foreground">{catalog.policy.goal || '填写目标后，选择适合的模块组成每日运营流程。'}</p>
      <p className="text-xs text-muted-foreground">
        {catalog.next_at
          ? `下次计划执行：${new Date(catalog.next_at).toLocaleString('zh-CN', { timeZone: catalog.policy.timezone })} · ${catalog.policy.timezone}`
          : '启用计划后显示下一次执行时间'}
      </p>
      {catalog.policy.enabled && catalog.schedule_state !== 'ready' && (
        <p className="text-muted-foreground">调度任务已暂停或缺失，请重新应用蓝图恢复。</p>
      )}
      {children}
    </header>
  )
}

function TemplateDetail({ template, onConfigure }: { template: BlueprintTemplate; onConfigure: () => void }) {
  return (
    <>
      <h2 className="text-lg font-semibold">{template.title}</h2>
      <p>{template.description}</p>
      <p className="text-muted-foreground">产出：{template.output}</p>
      {template.kind === 'business' && (
        <div className="space-y-2">
          <p>可选子类：{template.subtypes?.join('、')}</p>
          <p>目标受众：{template.defaults?.audience}</p>
          <p>内容方向：{template.content_directions?.join('、')}</p>
          <p>推荐先运行信息采集、草稿生产和日报；发布与互动可在下一步按需选择授权。</p>
        </div>
      )}
      {template.defaults && (
        <p className="text-muted-foreground">
          建议目标：{template.defaults.goal} 建议风格：{template.defaults.style}
          。已填写的目标和风格会保留，可在配置时修改。
        </p>
      )}
      <div className="space-y-1">
        <h3 className="font-medium">执行安排（可修改）</h3>
        {Object.entries(template.times).map(([module, times]) => (
          <p key={module}>
            {moduleLabels[module] || module}：{times.join('、')}
          </p>
        ))}
      </div>
      <p>
        运行条件：
        {template.modules.some(m => ['publish', 'comments', 'dm', 'follow'].includes(m))
          ? '账号登录、对应动作授权、额度和资料齐备；网页执行需要 Desktop 在线。'
          : '主题与目标已填写，Server 保持运行。内容生产需要可追溯来源。'}
      </p>
      {template.missing.length > 0 && <p>需要完善：{template.missing.join('；')}</p>}
      <Button onClick={onConfigure}>
        {template.kind === 'business'
          ? '使用此业务主题'
          : template.kind === 'scenario'
            ? '使用场景并调整'
            : template.status === '未加入'
              ? '配置并加入计划'
              : '调整当前计划'}
      </Button>
    </>
  )
}
