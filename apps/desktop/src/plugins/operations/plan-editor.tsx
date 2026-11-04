import { Button, Codicon, type CronBlueprintOwner, host, type PluginContext } from '@hermes/plugin-sdk'
import { lazy, Suspense, useMemo, useState } from 'react'

import { FirstRunProgress } from './first-run'
import { PlanForm } from './plan-form'
import { PlanReadiness } from './plan-readiness'
import { PlanSave } from './plan-save'
import { SharedModelBudget } from './shared-model-budget'
import { usePlanEditor } from './use-plan-editor'

const LibraryPage = lazy(() => import('./library-page').then(m => ({ default: m.LibraryPage })))

interface Props {
  ctx: PluginContext
  owner: CronBlueprintOwner
  compact?: boolean
}

export function PlanEditor({ ctx, owner, compact }: Props) {
  const bound = useMemo<PluginContext>(
    () => ({ ...ctx, rest: (path, options) => ctx.rest(path, { ...options, owner }) }),
    [ctx, owner]
  )

  return <OwnedEditor compact={compact} ctx={bound} key={JSON.stringify(owner)} />
}

function OwnedEditor({ ctx, compact }: { ctx: PluginContext; compact?: boolean }) {
  const editor = usePlanEditor(ctx)
  const [history, setHistory] = useState(false)
  const [expanded, setExpanded] = useState(!compact)
  const { catalog, policy, preview, busy, error, notice, change } = editor

  if (!catalog || !policy) {
    return (
      <div className="p-4" role="status">
        {error || '正在读取运营计划…'}
        {error && (
          <Button onClick={() => host.navigate('/settings?tab=plugins')} variant="link">
            管理插件
          </Button>
        )}
      </div>
    )
  }

  const first = catalog.version === 0

  return (
    <section
      aria-label={first ? '快速开始' : '运营计划设置'}
      className="@container mx-auto max-w-4xl space-y-5 p-4 text-sm"
    >
      <header className="flex items-center gap-2">
        <Codicon name="rocket" />
        <h2 className="text-lg font-semibold">{first ? '开始你的日常运营' : '运营计划'}</h2>
        <Button onClick={() => setExpanded(!expanded)} size="sm" variant="ghost">
          {expanded ? '收起设置' : '调整设置'}
        </Button>
      </header>
      {!first && <PlanControls editor={editor} />}
      {(first || expanded) && (
        <>
          <PlanForm catalog={catalog} change={change} policy={policy} />
          <SharedModelBudget ctx={ctx} />
          {catalog.draft?.version === catalog.version && (
            <Button onClick={() => change(catalog.draft!.policy)} variant="outline">
              恢复之前保存的配置草稿
            </Button>
          )}
          {preview?.readiness && <PlanReadiness rows={preview.readiness} />}
          {preview?.blocking?.length ? <p role="alert">{preview.blocking.join('；')}</p> : null}
          <PlanSave {...editor} first={first} />
          <p className="text-xs text-muted-foreground">
            快速首轮最多读取 20 条、检索 3 个查询；每日上限仍为 {policy.limits.source.toLocaleString()}{' '}
            条。缺少运行条件不会阻止保存。
          </p>
        </>
      )}
      {error && (
        <p className="text-destructive" role="alert">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <FirstRunProgress ctx={ctx} />
      {!first && (
        <details onToggle={event => setHistory(event.currentTarget.open)}>
          <summary className="cursor-pointer">运营台账与临时任务</summary>
          {history && (
            <Suspense fallback={<p>正在加载…</p>}>
              <LibraryPage ctx={ctx} section="history" />
            </Suspense>
          )}
        </details>
      )}
    </section>
  )
}

function PlanControls({ editor }: { editor: ReturnType<typeof usePlanEditor> }) {
  const { catalog, busy, control } = editor
  const policy = catalog!.policy
  const paused = policy.paused || !policy.enabled

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span>{policy.paused ? '全局暂停' : policy.enabled ? '计划已启用' : '计划已保存'}</span>
      <Button disabled={busy} onClick={() => void control(paused ? 'resume' : 'pause')} variant="outline">
        {paused ? '启用／恢复计划' : '全局暂停'}
      </Button>
      <Button disabled={busy || paused} onClick={() => void control('run')} variant="outline">
        立即执行
      </Button>
    </div>
  )
}
