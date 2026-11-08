import { Button, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'

import { $workspaces, ownerKey, scopeKey } from '../workspace-state'

import { writer, type Writer } from './controller'
import { WritingEditor } from './editor'
import { journal } from './journal'
import { writingPath } from './navigation'
import { WritingPanels } from './panels'
import { base, type Draft } from './types'

interface PageProps { ctx: PluginContext }
interface SessionProps extends PageProps { controller: Writer }

export function WritingPage({ ctx }: PageProps) {
  const [params, setParams] = useSearchParams(),
    [controller, setController] = useState<Writer | null>(null),
    [error, setError] = useState(''),
    [retry, setRetry] = useState(0)

  const owner = useValue(host.state.requestOwner),
    scope = useValue($workspaces)[ownerKey(owner)]?.selected

  const identity = params.get('draft'),
    creating = params.get('new'),
    source = params.get('from_content')

  const ownerScope = scope ? scopeKey(owner, scope) : ''
  useEffect(() => {
    if (!ownerScope) {
      return
    }

    let live = true,
      instance: Writer | undefined

    setController(null)
    setError('')

    const load = async () => {
      if (!identity) {
        if (!creating) {
          setParams(
            old => {
              const next = new URLSearchParams(old)
              next.set('new', crypto.randomUUID())

              return next
            },
            { replace: true }
          )

          return
        }

        const created = await ctx.rest<{ id: string }>(base, {
          method: 'POST',
          body: { id: creating, request_id: creating, ...(source ? { from_content: source } : {}) }
        })

        if (live) {
          setParams(
            old => {
              const next = new URLSearchParams(old)
              next.set('draft', created.id)
              next.delete('new')
              next.delete('from_content')

              return next
            },
            { replace: true }
          )
        }

        return
      }

      const key = JSON.stringify([ownerScope, identity]),
        local = await journal(key)

      let draft: Draft

      try {
        draft = await ctx.rest<Draft>(`${base}/${identity}`)
      } catch (reason) {
        if (!local || /40[134]/.test(String(reason))) {
          throw reason
        }

        draft = local.draft
      }

      if (!live) {
        return
      }

      const recovered = local && (local.dirty || local.pending) ? local : { draft, dirty: false }
      instance = writer(ctx, key, recovered)
      setController(instance)

      if (recovered.dirty || recovered.pending) {
        void instance.save().catch(() => undefined)
      }
    }

    void load().catch(reason => {
      if (live) {
        setError(String(reason))
      }
    })

    return () => {
      live = false
      instance?.dispose()
    }
  }, [ctx, identity, creating, source, ownerScope, retry, setParams])

  return controller ? (
    <WritingSession controller={controller} ctx={ctx} />
  ) : (
    <div className="p-6">
      <p role="status">{error || '正在打开写作草稿…'}</p>
      {error && <Button onClick={() => setRetry(n => n + 1)}>重试</Button>}
    </div>
  )
}

function WritingSession({ controller, ctx }: SessionProps) {
  const state = useValue(controller.state),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [submitted, setSubmitted] = useState(''),
    [epoch, setEpoch] = useState(0)

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError('')

    try {
      await fn()
    } catch (reason) {
      setError(String(reason))
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
        event.preventDefault()
        void controller.save().catch(reason => setError(String(reason)))
      }
    }

    const unload = (event: BeforeUnloadEvent) => {
      if (controller.state.get().dirty || controller.state.get().pending) {
        event.preventDefault()
        event.returnValue = ''
      }
    }

    const online = () => {
      void controller.save().catch(() => undefined)
    }

    window.addEventListener('keydown', key)
    window.addEventListener('beforeunload', unload)
    window.addEventListener('online', online)
    window.addEventListener('focus', online)

    return () => {
      window.removeEventListener('keydown', key)
      window.removeEventListener('beforeunload', unload)
      window.removeEventListener('online', online)
      window.removeEventListener('focus', online)
    }
  }, [controller])

  return (
    <main className="flex min-h-full flex-col">
      <header className="flex flex-wrap items-center gap-2 border-b p-3">
        <Button
          onClick={() =>
            void act(async () => {
              await controller.save()
              host.navigate('/content?tab=writing')
            })
          }
          variant="ghost"
        >
          返回草稿
        </Button>
        <span className="mr-auto text-sm" role="status">
          {state.status}
        </span>
        <Button disabled={busy || state.conflict} onClick={() => void act(controller.save)} variant="outline">
          保存草稿 ⌘S
        </Button>
        <Button
          disabled={busy || state.conflict || state.draft.archived}
          onClick={() => void act(async () => setSubmitted((await controller.submit()).content_id))}
        >
          提交审核
        </Button>
      </header>
      {(state.error || error) && (
        <p className="p-3" role="alert">
          {error || state.error}
        </p>
      )}
      <div className="flex flex-wrap gap-2 px-4 py-2">
        <Button
          disabled={busy}
          onClick={() => void act(async () => host.navigate(writingPath(`draft=${(await controller.copy()).id}`)))}
          size="sm"
          variant="ghost"
        >
          另存副本
        </Button>
        {state.conflict && (
          <Button
            disabled={busy}
            onClick={() =>
              void act(async () => {
                await controller.reload()
                setEpoch(n => n + 1)
              })
            }
            size="sm"
            variant="outline"
          >
            放弃本机修改，载入服务器版本
          </Button>
        )}
        {submitted && (
          <Button onClick={() => host.navigate(`/content?tab=drafts&record=${submitted}`)} variant="link">
            已提交，前往审核与排期
          </Button>
        )}
      </div>
      <fieldset className="min-w-0 flex-1" disabled={busy || state.draft.archived}>
        <input
          aria-label="稿件标题"
          className="w-full border-b bg-background px-8 py-5 text-2xl font-semibold outline-none"
          maxLength={200}
          onChange={event => controller.edit({ title: event.target.value })}
          placeholder="为文章写一个标题"
          value={state.draft.title}
        />
        <p className="px-8 py-2 text-xs text-muted-foreground">
          支持长文暂存 · 上传或粘贴图片即确认具有使用权限 · 未提交审核的草稿不会发布
        </p>
        <div className="flex flex-col xl:flex-row">
          <WritingEditor controller={controller} ctx={ctx} disabled={busy || state.draft.archived} key={epoch} />
          <WritingPanels controller={controller} ctx={ctx} />
        </div>
      </fieldset>
    </main>
  )
}
