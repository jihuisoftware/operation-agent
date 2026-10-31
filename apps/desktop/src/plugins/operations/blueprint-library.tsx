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

import { type BlueprintCatalog, type BlueprintTemplate } from './blueprint-types'
import { BlueprintWizard } from './blueprint-wizard'
import { PlatformLoginsPanel } from './platform-logins'
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
  const categories = ['全部', ...new Set(catalog.templates.filter(t => t.id !== 'daily').map(t => t.category))]

  return (
    <div className="space-y-4 p-4 text-sm">
      <PlanHeader catalog={catalog} owner={owner}>
        {resources}
      </PlanHeader>
      <PlatformLoginsPanel compact={view === 'summary'} ctx={ctx} owner={owner} />
      {error && (
        <p className="text-destructive" role="alert">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {view === 'blueprints' && (
        <>
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
              <TemplateRow
                onSelect={() => choose(catalog.templates[0])}
                selected={selected === 'daily'}
                template={catalog.templates[0]}
              />
              <div className="overflow-x-auto">
                <SegmentedControl
                  onChange={setCategory}
                  options={categories.map(id => ({ id, label: id }))}
                  sizing="content"
                  value={category}
                />
              </div>
              <div>
                {catalog.templates
                  .filter(t => t.id !== 'daily' && (category === '全部' || t.category === category))
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
      <p>
        运行条件：
        {template.modules.some(m => ['publish', 'comments', 'dm', 'follow'].includes(m))
          ? '账号登录、对应动作授权、额度和资料齐备；网页执行需要 Desktop 在线。'
          : '主题与目标已填写，Server 保持运行。内容生产需要可追溯来源。'}
      </p>
      {template.missing.length > 0 && <p>需要完善：{template.missing.join('；')}</p>}
      <Button onClick={onConfigure}>{template.status === '未加入' ? '配置并加入计划' : '调整当前计划'}</Button>
    </>
  )
}
