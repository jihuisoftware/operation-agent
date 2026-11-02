import {
  Badge,
  Button,
  Codicon,
  type CronBlueprintOwner,
  host,
  type PluginContext,
  RowButton,
  useValue
} from '@hermes/plugin-sdk'
import { useMemo } from 'react'
import { useSearchParams } from 'react-router'

import { moduleLabels } from './blueprint-types'
import { FirstRunProgress } from './first-run'
import { LibraryPage } from './library-page'
import { type OverviewData, useOverview } from './overview-data'
import { Empty, Open, Region, ReportTime, overviewRoutes as routes, RunState, Time } from './overview-ui'
import { PlanEditor } from './plan-editor'
import { WorkspaceSummary } from './workspace-summary'
import { TokenUsageCard } from './token-usage/card'

export function OverviewPage({ ctx }: { ctx: PluginContext }) {
  const owner = useValue(host.state.requestOwner)
  const [params] = useSearchParams()

  return <OwnedOverview ctx={ctx} key={JSON.stringify(owner)} owner={owner} tab={params.get('tab') || ''} />
}

export function OwnedOverview({
  ctx,
  owner,
  tab = ''
}: {
  ctx: PluginContext
  owner: CronBlueprintOwner
  tab?: string
}) {
  const { data, error, retry } = useOverview(ctx, owner)

  const bound = useMemo<PluginContext>(
    () => ({ ...ctx, rest: (path, options) => ctx.rest(path, { ...options, owner }) }),
    [ctx, owner]
  )

  return (
    <main aria-label="运营总览" className="@container h-full overflow-auto p-5 text-sm">
      <div className="mx-auto max-w-6xl space-y-5">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold">首页</h1>
            <Badge variant="muted">
              <Codicon name="account" />
              {owner.profile || 'default'}
            </Badge>
          </div>
          <div className="flex items-center gap-1">
            <Open to="/cron">
              <Codicon name="calendar" />
              定时任务
            </Open>
            <Button aria-label="刷新" onClick={retry} size="icon-sm" variant="ghost">
              <Codicon name="refresh" />
            </Button>
          </div>
        </header>
        <WorkspaceSummary ctx={bound} />
        <TokenUsageCard ctx={bound} />
        {error && (
          <p className="text-destructive" role="alert">
            总览更新失败，已显示的数据可能过期。{error}
          </p>
        )}
        {!data && !error && (
          <p role="status">
            <Codicon name="loading" spinning /> 正在读取运营记录…
          </p>
        )}
        {data && tab === 'reports' ? (
          <LibraryPage ctx={bound} section="reports" />
        ) : (
          data && (
            <>
              {!data.topic && <PlanEditor ctx={ctx} owner={owner} />}
              {data.topic && <OverviewContent data={data} />}
              {data.topic && <FirstRunProgress ctx={bound} />}
            </>
          )
        )}
      </div>
    </main>
  )
}

function OverviewContent({ data }: { data: OverviewData }) {
  return (
    <>
      <section aria-label="运营目标" className="space-y-3 border-b pb-4">
        <div className="flex flex-wrap items-center gap-2">
          <Codicon className="text-primary" name="target" size={22} />
          <h2 className="mr-auto text-lg font-medium">{data.topic || '设置你的运营主题'}</h2>
          <Badge variant={!data.enabled ? 'muted' : data.paused ? 'warn' : 'success'}>
            <Codicon name={!data.enabled ? 'circle-outline' : data.paused ? 'debug-pause' : 'play'} />
            {!data.enabled ? '未启用' : data.paused ? '已暂停' : '已启用'}
          </Badge>
          <Badge variant={data.online ? 'success' : 'warn'}>
            <Codicon name="device-desktop" />
            {data.online ? '执行器在线' : '执行器离线'}
          </Badge>
        </div>
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer">目标与规则</summary>
          <p className="my-2 whitespace-pre-wrap break-words">{data.goal || '选择业务场景，设置主题与目标。'}</p>
          <Open to={routes.rules}>编辑目标与规则</Open>
        </details>
      </section>
      <Metrics data={data} />
      <div className="grid items-start gap-4 @[50rem]:grid-cols-2">
        <Region icon="graph" title="数据与行业分析" to="/analysis">
          {data.analysis?.length ? (
            data.analysis.map(item => (
              <div key={item.id}>
                <p>{item.detail}</p>
                <Time value={item.created} />
              </div>
            ))
          ) : (
            <Empty icon="graph">暂无分析报告</Empty>
          )}
          <Open to="/analysis?tab=industry">查看行业结论</Open>
        </Region>
        <Attention data={data} />
        <RecentRuns data={data} />
        <Schedule data={data} />
        <Publications data={data} />
        <Accounts data={data} />
        <Region icon="notebook" title="日报与复盘" to={routes.reports}>
          {data.report ? (
            <div className="flex items-center gap-3">
              <Codicon className="text-primary" name="file-text" size={28} />
              <div className="space-y-1">
                <p className="font-medium">{data.report.day} 运营日报</p>
                <p className="text-xs text-muted-foreground">
                  <ReportTime value={data.report.created} />
                </p>
              </div>
            </div>
          ) : (
            <Empty icon="file-text">暂无日报</Empty>
          )}
          <Badge variant={data.report?.day === data.day ? 'success' : 'muted'}>
            {data.report?.day === data.day ? '今日已生成' : '今日待生成'}
          </Badge>
        </Region>
      </div>
      <details className="space-y-2 text-xs text-muted-foreground">
        <summary className="cursor-pointer">统计口径与更新时间</summary>
        <p>
          统计日期 {data.day} · 计划时区 {data.timezone} · 规则版本 {data.version}
        </p>
        <p>
          更新于 <Time value={data.updated_at} />
          ；页面时间按本机时区显示。
        </p>
        <p>发布与互动只计核对成功，结果未知的提交不计入成果。内容按版本统计，选题取今日最新一批。</p>
        <p>待处理覆盖历史，各分类可能指向同一事项；失败记录不表示需要重复执行。</p>
        <p>
          排期受调度器、在线状态及规则约束。登录保留最近确认状态，执行前仍核对。费用与平台指标以日报中可获取的数据为准。
        </p>
      </details>
    </>
  )
}

function Metrics({ data }: { data: OverviewData }) {
  const metrics = [
    { label: '采集来源', value: data.counts.sources, icon: 'search', to: routes.sources },
    { label: '候选选题', value: data.counts.topics, icon: 'lightbulb', to: routes.topics },
    { label: '内容版本', value: data.counts.content, icon: 'file-media', to: routes.content },
    { label: '确认发布', value: data.counts.published, icon: 'send', to: routes.tasks },
    { label: '确认互动', value: data.counts.interactions, icon: 'comment-discussion', to: routes.tasks },
    { label: '模型调用', value: data.counts.model_calls, icon: 'sparkle', to: routes.reports }
  ]

  return (
    <section aria-label="今日成果" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">今日成果</h2>
        <span className="text-xs text-muted-foreground">{data.day}</span>
      </div>
      <div className="grid grid-cols-2 gap-3 @[32rem]:grid-cols-3 @[60rem]:grid-cols-6">
        {metrics.map(metric => (
          <RowButton
            aria-label={`查看${metric.label}`}
            className="min-w-0 space-y-3 rounded-lg bg-muted/40 p-4 text-left transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring"
            key={metric.label}
            onClick={() => host.navigate(metric.to)}
          >
            <div className="flex items-center justify-between text-primary">
              <Codicon name={metric.icon} size={20} />
              <Codicon className="text-muted-foreground" name="arrow-right" />
            </div>
            <p className="text-3xl font-semibold tabular-nums">{metric.value.toLocaleString()}</p>
            <p className="text-xs text-muted-foreground">{metric.label}</p>
          </RowButton>
        ))}
      </div>
      <p className="flex items-center gap-1 text-xs text-muted-foreground">
        <Codicon name="check" />
        来源正文已取得 {data.counts.sources_read} 条
      </p>
    </section>
  )
}

function Attention({ data }: { data: OverviewData }) {
  const rows = [
    { label: '结果待核对', count: data.pending.unverified, icon: 'inspect', to: routes.tasks },
    { label: '人工咨询', count: data.pending.inbox, icon: 'comment', to: routes.tasks },
    { label: '内容待完善', count: data.pending.content, icon: 'edit', to: routes.content },
    { label: '今日失败任务', count: data.pending.failed_today, icon: 'error', to: routes.tasks }
  ]

  return (
    <Region icon="checklist" title="待处理事项" to={routes.tasks}>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        {rows.map(row => (
          <RowButton
            aria-label={`处理${row.label}`}
            className="flex min-w-0 items-center gap-2 rounded py-3 text-left hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring"
            key={row.label}
            onClick={() => host.navigate(row.to)}
          >
            <Codicon className="text-muted-foreground" name={row.icon} />
            <span className="flex-1 text-xs">{row.label}</span>
            <Badge variant={row.count ? 'warn' : 'muted'}>{row.count}</Badge>
          </RowButton>
        ))}
      </div>
    </Region>
  )
}

function RecentRuns({ data }: { data: OverviewData }) {
  return (
    <Region icon="pulse" title="最近执行" to="/cron?tab=running">
      {!data.runs.length && <Empty icon="history">今日暂无执行记录</Empty>}
      {data.runs.slice(0, 3).map(run => (
        <details className="group space-y-2" key={run.id}>
          <summary className="flex cursor-pointer list-none items-start gap-2 [&::-webkit-details-marker]:hidden">
            <Codicon className="mt-0.5 text-muted-foreground group-open:rotate-90" name="chevron-right" />
            <span className="min-w-0 flex-1">
              <span className="block">{moduleLabels[run.stage] || run.stage}</span>
              <span className="text-xs text-muted-foreground">
                <Time value={run.started} />
              </span>
            </span>
            <RunState state={run.state} />
          </summary>
          <p className="whitespace-pre-wrap break-words text-xs select-text">
            {run.detail || '暂无结果说明'}
            {run.detail.length >= 600 && '…'}
          </p>
          <Open to={routes.tasks}>完整执行记录</Open>
        </details>
      ))}
      {data.runs.length > 3 && (
        <Open to={routes.tasks}>
          更多执行记录
          <Codicon name="arrow-right" />
        </Open>
      )}
    </Region>
  )
}

function Schedule({ data }: { data: OverviewData }) {
  return (
    <Region icon="calendar" title="后续计划时段" to="/cron?tab=upcoming">
      {!data.schedule.length && <Empty icon="calendar">暂无启用中的排期</Empty>}
      <ol className="space-y-3">
        {data.schedule.slice(0, 3).map((item, index) => (
          <li className="flex items-center gap-3" key={`${item.module}:${item.time}`}>
            <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs text-primary">
              {index + 1}
            </span>
            <div>
              <p>{item.label}</p>
              <p className="text-xs text-muted-foreground">
                <Time value={item.next_at} />
              </p>
            </div>
          </li>
        ))}
      </ol>
    </Region>
  )
}

function Publications({ data }: { data: OverviewData }) {
  return (
    <Region icon="send" title="今日已确认发布" to={routes.tasks}>
      {!data.publications.length && <Empty icon="file-media">暂无确认发布</Empty>}
      {data.publications.map(item => (
        <details className="space-y-2" key={item.id}>
          <summary className="cursor-pointer font-medium">{item.title || '已发布内容'}</summary>
          <p className="text-xs text-muted-foreground">
            账号：{item.account_id || '未记录'} · 动作创建于 <Time value={item.created} />
          </p>
          <p className="break-all text-xs select-text">{item.url || '未取得链接，请在执行记录查看核对证据。'}</p>
        </details>
      ))}
    </Region>
  )
}

function Accounts({ data }: { data: OverviewData }) {
  return (
    <Region icon="account" title="账号登录" to="/accounts">
      <div className="space-y-3">
        {data.platforms.map(platform => {
          const attention = platform.account_mismatch || platform.observed_state === 'verification'
          const loggedIn = platform.state === 'logged_in' && !attention

          const label = platform.account_mismatch
            ? '账号不匹配'
            : attention
              ? '需验证'
              : loggedIn
                ? '已登录'
                : platform.state === 'logged_out'
                  ? '已退出或过期'
                  : '待检查'

          return (
            <div className="flex items-center justify-between gap-2" key={platform.id} title={platform.reason}>
              <span className="flex items-center gap-2">
                <Codicon className="text-muted-foreground" name="globe" />
                {platform.name}
              </span>
              <Badge variant={loggedIn ? 'success' : attention ? 'warn' : 'muted'}>
                <Codicon name={loggedIn ? 'check' : 'circle-outline'} />
                {label}
              </Badge>
            </div>
          )
        })}
      </div>
    </Region>
  )
}
