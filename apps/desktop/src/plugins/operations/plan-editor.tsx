import { Button, Codicon, type CronBlueprintOwner, host, type PluginContext } from '@hermes/plugin-sdk'
import { useState } from 'react'

import { PlanForm } from './plan-form'
import { PlanReadiness } from './plan-readiness'
import { PlanSave } from './plan-save'
import { ReviewPolicySettings } from './review-policy'
import { currentWorkspaceLink, guardWorkspaceChange, WORKSPACES_PATH } from './workspace-navigation'
import { useOwnerContext } from './use-owner-context'
import { usePlanEditor } from './use-plan-editor'

interface Props {
  ctx: PluginContext
  owner: CronBlueprintOwner
}

export function PlanEditor({ ctx, owner }: Props) {
  const bound = useOwnerContext(ctx, owner)

  return <OwnedEditor owner={owner} ctx={bound} key={JSON.stringify(owner)} />
}

function OwnedEditor({ ctx, owner }: Props) {
  const editor = usePlanEditor(ctx, owner)
  const [expanded, setExpanded] = useState(true)
  const { catalog, policy, preview, error, notice, change } = editor

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
        {!first && <Button onClick={() => setExpanded(!expanded)} size="sm" variant="ghost">
          {expanded ? '收起设置' : '调整设置'}
        </Button>}
      </header>
      {!first && <PlanControls editor={editor} />}
      {(first || expanded) && (
        <>
          <PlanForm catalog={catalog} change={change} policy={policy} />
          <Button onClick={() => guardWorkspaceChange(owner, () => host.navigate(WORKSPACES_PATH + '?view=settings'))} variant="link">管理全部业务的共享模型预算</Button>
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
      <ReviewPolicySettings ctx={ctx} onDirty={editor.reviewChanged} />
      <Button onClick={() => guardWorkspaceChange(owner, () => host.navigate(currentWorkspaceLink('history', owner)))} variant="link">查看运营台账与临时任务</Button>
    </section>
  )
}

function PlanControls({ editor }: { editor: ReturnType<typeof usePlanEditor> }) {
  const { catalog, busy, control } = editor
  const policy = catalog!.policy
  const paused = policy.paused || !policy.enabled

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span>{policy.paused ? '本主题已暂停' : policy.enabled ? '计划已启用' : '计划已保存'}</span>
      <Button disabled={busy} onClick={() => void control(paused ? 'resume' : 'pause')} variant="outline">
        {paused ? '启用／恢复本主题' : '暂停本主题'}
      </Button>
      <Button disabled={busy || paused} onClick={() => void control('run')} variant="outline">
        立即执行
      </Button>
    </div>
  )
}
