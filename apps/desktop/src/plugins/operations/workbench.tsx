import { type CronBlueprintOwner, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { AccountSelection } from './account-selection'
import { moduleLabels } from './blueprint-types'
import { ActionManager, ContentEditor } from './management'
import { $showOperationsBrowser } from './state'
import type { OperationsState, Policy, RecordRow } from './types'

const labels: Record<string, string> = {
  source: '读取来源',
  publish: '发布图文',
  comment: '主动评论',
  reply: '评论回复',
  dm: '私信回复',
  follow: '条件回关'
}

const stages = moduleLabels

const tabs = ['目标与规则', '素材与内容', '任务与执行', '来源与数据', '每日总结']

export function Workbench({
  ctx,
  owner,
  initialTab
}: {
  ctx: PluginContext
  owner?: CronBlueprintOwner
  initialTab?: string
}) {
  const ambient = useValue(host.state.requestOwner)
  const scope = owner || ambient

  const owned = useMemo<PluginContext>(
    () => ({ ...ctx, rest: (path, options) => ctx.rest(path, { ...options, owner: scope }) }),
    [ctx, scope]
  )

  return (
    <OwnedWorkbench
      canView={
        ambient.connectionId === scope.connectionId && (ambient.profile || 'default') === (scope.profile || 'default')
      }
      ctx={owned}
      initialTab={initialTab}
      key={JSON.stringify(scope)}
    />
  )
}

function OwnedWorkbench({ ctx, initialTab, canView }: { ctx: PluginContext; initialTab?: string; canView: boolean }) {
  const [state, setState] = useState<OperationsState | null>(null)
  const [draft, setDraft] = useState<Policy | null>(null)
  const [version, setVersion] = useState(0)
  const [dirty, setDirty] = useState(false)
  const [tab, setTab] = useState(initialTab || tabs[0])
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    const next = await ctx.rest<OperationsState>('/state')
    setState(next)

    return next
  }, [ctx])

  useEffect(() => {
    let cancelled = false
    void refresh()
      .then(next => {
        if (!cancelled) {
          setDraft(next.policy)
          setVersion(next.version)
        }
      })
      .catch(error => setError(String(error)))
    const timer = setInterval(() => void refresh().catch(error => setError(String(error))), 5000)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [refresh])

  useEffect(() => {
    if (state && !dirty) {
      setDraft(state.policy)
      setVersion(state.version)
    }
  }, [state, dirty])

  const save = async (policy: Policy) => {
    try {
      await ctx.rest('/policy', { method: 'PUT', body: { version, policy } })
      const next = await refresh()
      setDraft(next.policy)
      setVersion(next.version)
      setDirty(false)
      setError('已保存')
    } catch (error) {
      setError(String(error))
    }
  }

  if (!state || !draft) {
    return <div className="p-6">{error || '正在加载运营工作台…'}</div>
  }

  const field = (key: keyof Policy, value: unknown) => {
    setDirty(true)
    setDraft({ ...draft, [key]: value })
  }

  return (
    <div className="h-full overflow-auto p-5 text-sm">
      <header className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">每日自动运营</h1>
        <span>{state.online ? '桌面执行器在线' : '等待桌面执行器'}</span>
        <button disabled={!canView} onClick={() => $showOperationsBrowser.set(true)}>
          查看执行网页
        </button>
        <button
          onClick={() =>
            void ctx
              .rest<OperationsState>('/state')
              .then(current =>
                ctx.rest('/policy', {
                  method: 'PUT',
                  body: { version: current.version, policy: { ...current.policy, paused: true } }
                })
              )
              .then(refresh)
              .catch(error => setError(String(error)))
          }
        >
          立即暂停
        </button>
      </header>
      <nav className="mb-4 flex flex-wrap gap-3">
        {tabs.map(name => (
          <button aria-pressed={tab === name} key={name} onClick={() => setTab(name)}>
            {name}
          </button>
        ))}
      </nav>
      {error && (
        <p className="mb-3" role="status">
          {error}
        </p>
      )}
      {tab === tabs[0] && (
        <div className="grid max-w-4xl gap-3">
          <p>启用后按以下规则自动执行；Mac 和 Desktop 需保持运行。</p>
          <AccountSelection onChange={next => field('account_id', next.account_id)} policy={draft} />
          {(
            [
              ['topic', '运营主题'],
              ['brand', '项目／品牌档案'],
              ['goal', '运营目标'],
              ['audience', '目标受众'],
              ['style', '内容风格'],
              ['timezone', '时区'],
              ['deadline', '截止日期（可空）']
            ] as const
          ).map(([key, label]) => (
            <label className="grid gap-1" key={key}>
              {label}
              <input
                className="rounded border bg-transparent p-2"
                onChange={e => field(key, e.target.value)}
                value={draft[key]}
              />
            </label>
          ))}
          {(
            [
              ['sources', '指定网页地址'],
              ['rss_sources', 'RSS / Atom 订阅地址'],
              ['keywords', '检索关键词'],
              ['knowledge', '已确认的回复知识'],
              ['follow_terms', '回关匹配词（空时不回关）']
            ] as const
          ).map(([key, label]) => (
            <label className="grid gap-1" key={key}>
              {label}（每行一条）
              <textarea
                className="rounded border bg-transparent p-2"
                onChange={e => field(key, e.target.value.split('\n'))}
                rows={3}
                value={draft[key].join('\n')}
              />
            </label>
          ))}
          <label>
            目标优先级（1 最高）{' '}
            <input
              className="w-16 border bg-transparent"
              max={5}
              min={1}
              onChange={e => field('priority', Number(e.target.value))}
              type="number"
              value={draft.priority}
            />
          </label>
          <label>
            每日模型调用上限{' '}
            <input
              className="w-20 border bg-transparent"
              max={1000}
              min={0}
              onChange={e => field('model_calls', Number(e.target.value))}
              type="number"
              value={draft.model_calls}
            />
          </label>
          <div className="flex flex-wrap gap-4">
            {Object.entries(moduleLabels).map(([module, label]) => (
              <label key={module}>
                <input
                  checked={draft.modules[module]}
                  onChange={e => field('modules', { ...draft.modules, [module]: e.target.checked })}
                  type="checkbox"
                />
                {label}
              </label>
            ))}
          </div>
          <div className="flex flex-wrap gap-4">
            {Object.keys(draft.allowed).map(kind => (
              <label key={kind}>
                <input
                  checked={draft.allowed[kind]}
                  onChange={e => field('allowed', { ...draft.allowed, [kind]: e.target.checked })}
                  type="checkbox"
                />{' '}
                {labels[kind]}
              </label>
            ))}
          </div>
          <div className="flex flex-wrap gap-3">
            {Object.entries(draft.limits).map(([kind, value]) => (
              <label key={kind}>
                {labels[kind]}／天{' '}
                <input
                  className="w-16 border bg-transparent"
                  max={1000}
                  min={0}
                  onChange={e => field('limits', { ...draft.limits, [kind]: Number(e.target.value) })}
                  type="number"
                  value={value}
                />
              </label>
            ))}
          </div>
          {Object.entries(draft.times).map(([stage, values]) => (
            <label key={stage}>
              {stages[stage]}时间{' '}
              <input
                className="border bg-transparent p-1"
                onChange={e =>
                  field('times', { ...draft.times, [stage]: e.target.value.split(',').map(v => v.trim()) })
                }
                value={values.join(',')}
              />
            </label>
          ))}
          <label>
            <input checked={draft.enabled} onChange={e => field('enabled', e.target.checked)} type="checkbox" />{' '}
            启用规则范围内的自动运营
          </label>
          <label>
            <input checked={draft.paused} onChange={e => field('paused', e.target.checked)} type="checkbox" />{' '}
            暂停执行（取消勾选后保存以恢复）
          </label>
          <button className="w-fit rounded border px-4 py-2" onClick={() => void save(draft)}>
            保存规则与时间表
          </button>
        </div>
      )}
      {tab === tabs[1] && (
        <>
          <Assets content={state.content} ctx={ctx} onError={setError} refresh={refresh} rows={state.asset} />
          <ContentEditor
            assets={state.asset}
            ctx={ctx}
            onError={setError}
            refresh={refresh}
            rows={state.content}
            sources={state.source}
          />
        </>
      )}
      {tab === tabs[2] && (
        <>
          <NewRecord ctx={ctx} kind="task" onError={setError} onSaved={refresh} />
          <Records rows={[...state.task, ...state.runs, ...state.inbox, ...state.block, ...state.events]} />
          <ActionManager ctx={ctx} onError={setError} refresh={refresh} rows={state.actions} />
        </>
      )}
      {tab === tabs[3] && (
        <>
          <NewRecord ctx={ctx} kind="metric" onError={setError} onSaved={refresh} />
          <Records rows={[...state.source, ...state.brief, ...state.metric]} />
        </>
      )}
      {tab === tabs[4] &&
        state.report.map(report => (
          <article className="mb-5 rounded border p-3" key={report.id}>
            <button onClick={() => download(String(report.day), String(report.markdown))}>
              导出 {String(report.day)} 日报
            </button>
            <pre className="whitespace-pre-wrap text-sm">{String(report.markdown)}</pre>
          </article>
        ))}
    </div>
  )
}

function Records({ rows }: { rows: RecordRow[] }) {
  return (
    <div className="grid gap-2">
      {rows.length ? (
        rows.map(row => (
          <details className="rounded border p-2" key={row.id}>
            <summary>
              {String(row.title || row.name || row.stage || row.kind || row.id)} · {String(row.state || row.day || '')}
            </summary>
            <pre className="overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(row, null, 2)}</pre>
          </details>
        ))
      ) : (
        <p>暂无记录；执行后会显示实际结果。</p>
      )}
    </div>
  )
}

function NewRecord({
  ctx,
  kind,
  onSaved,
  onError
}: {
  ctx: PluginContext
  kind: string
  onSaved: () => Promise<unknown>
  onError: (error: string) => void
}) {
  const [text, setText] = useState('')

  return (
    <div className="mb-4 flex gap-2">
      <textarea
        className="flex-1 border bg-transparent p-2"
        onChange={e => setText(e.target.value)}
        placeholder={
          kind === 'task'
            ? '补充当日任务、优先级或截止要求'
            : '导入指标 JSON：包含 id、day、name、value、definition、source；缺失值填 null'
        }
        value={text}
      />
      <button
        onClick={() => {
          try {
            const body =
              kind === 'task' ? { text, created: new Date().toISOString(), state: 'pending' } : JSON.parse(text)

            void ctx
              .rest(`/records/${kind}`, { method: 'POST', body })
              .then(onSaved)
              .then(() => setText(''))
              .catch(error => onError(String(error)))
          } catch (error) {
            onError(String(error))
          }
        }}
      >
        添加{kind === 'task' ? '任务' : '指标'}
      </button>
    </div>
  )
}

function Assets({
  ctx,
  rows,
  content,
  refresh,
  onError
}: {
  ctx: PluginContext
  rows: RecordRow[]
  content: RecordRow[]
  refresh: () => Promise<unknown>
  onError: (error: string) => void
}) {
  const [authorized, setAuthorized] = useState(false)

  return (
    <div className="grid gap-3">
      <label>
        <input checked={authorized} onChange={e => setAuthorized(e.target.checked)} type="checkbox" />{' '}
        我确认所选素材可用于当前账号公开发布
      </label>
      <input
        accept="image/png,image/jpeg,image/webp"
        disabled={!authorized}
        multiple
        onChange={async e => {
          try {
            for (const file of Array.from(e.target.files || [])) {
              if (file.size > 20 * 1024 * 1024) {
                throw new Error('图片不能超过 20 MB')
              }

              const data = await new Promise<string>((resolve, reject) => {
                const reader = new FileReader()
                reader.onload = () => resolve(String(reader.result).split(',')[1])
                reader.onerror = reject
                reader.readAsDataURL(file)
              })

              await ctx.rest('/assets', { method: 'POST', body: { name: file.name, data, authorized } })
            }

            await refresh()
          } catch (error) {
            onError(String(error))
          }
        }}
        type="file"
      />
      <Records rows={rows} />
      {rows
        .filter(row => !row.revoked)
        .map(row => (
          <button
            key={row.id}
            onClick={() =>
              void ctx
                .rest(`/assets/${row.id}/revoke`, { method: 'POST', body: {} })
                .then(refresh)
                .catch(error => onError(String(error)))
            }
          >
            撤回素材授权：{String(row.name)}
          </button>
        ))}
      <h2>内容版本</h2>
      <Records rows={content} />
    </div>
  )
}

function download(day: string, markdown: string) {
  const url = URL.createObjectURL(new Blob([markdown], { type: 'text/markdown;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${day}-运营日报.md`
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
