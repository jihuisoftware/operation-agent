import { Button, host, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import { AssetImage } from './asset-image'
interface VisualSet {
  previous?: { pages: { asset_id: string; title: string }[] }
  selection?: { provider: string; model: string }
  id: string
  state: string
  detail: string
  pages: { asset_id: string; title: string; kind: string; has_art?: boolean }[]
  attempts: { state: string }[]
  review?: { pass: boolean | null; reason: string; issues?: string[] }
}
interface Props {
  ctx: PluginContext
  kind: 'content' | 'writing'
  identity: string
  compact?: boolean
  prepare: () => Promise<Record<string, unknown>>
  apply: (job: string) => Promise<void>
}

export function ImageStudio({ ctx, kind, identity, prepare, apply, compact }: Props) {
  const [job, setJob] = useState<VisualSet | null>(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState('')

  const jobId = job?.id
  const running = job?.state === 'queued' || job?.state === 'running'
  useEffect(() => {
    let live = true
    void ctx
      .rest<{ item: VisualSet | null }>(`/visual-sets?kind=${kind}&identity=${encodeURIComponent(identity)}`)
      .then(value => {
        if (live) {
          setJob(value.item)
        }
      })
      .catch(reason => {
        if (live) {
          setError(String(reason))
        }
      })

    return () => {
      live = false
    }
  }, [ctx, kind, identity])
  useEffect(() => {
    if (!running || !jobId) {
      return
    }

    let live = true,
      pending = false

    const timer = setInterval(async () => {
      if (pending) {
        return
      }

      pending = true

      try {
        const value = await ctx.rest<VisualSet>(`/visual-sets/${encodeURIComponent(jobId)}`)

        if (live) {
          setJob(value)
          setError('')
        }
      } catch (reason) {
        if (live) {
          setError(String(reason))
        }
      } finally {
        pending = false
      }
    }, 2000)

    return () => {
      live = false
      clearInterval(timer)
    }
  }, [ctx, jobId, running])

  const act = async (operation: () => Promise<void>) => {
    setBusy(true)
    setError('')
    setNotice('')

    try {
      await operation()
    } catch (reason) {
      setError(String(reason))
    } finally {
      setBusy(false)
    }
  }

  const generate = (retry: boolean, regenerate_art?: number) =>
    act(async () => {
      const body = await prepare()
      setJob(
        await ctx.rest<VisualSet>('/visual-sets', {
          method: 'POST',
          body: { ...body, kind, id: identity, retry, regenerate_art, request_id: crypto.randomUUID() }
        })
      )
    })

  return (
    <section aria-label="杂志组图" className="space-y-4 py-3">
      <p className="text-sm">
        清爽杂志与信息图 · 通常 3–6 页 · 最多 2 张 AI 主视觉，全篇额外最多尝试一次。中文和图表在本地精确排版。
      </p>
      <div className="flex flex-wrap gap-2">
        <Button disabled={busy || running} onClick={() => void generate(false)}>
          生成整套图文
        </Button>
        {job && !running && (job.state !== 'completed' || job.review?.pass !== true) && (
          <Button disabled={busy} onClick={() => void generate(true)} variant="outline">
            {job.state === 'completed' ? '重新视觉检查（复用配图）' : '重试未完成部分'}
          </Button>
        )}
        {running && (
          <Button
            disabled={busy}
            onClick={() =>
              void act(async () =>
                setJob(
                  await ctx.rest<VisualSet>(`/visual-sets/${encodeURIComponent(job!.id)}/cancel`, { method: 'POST' })
                )
              )
            }
            variant="outline"
          >
            取消生成
          </Button>
        )}
        <Button onClick={() => host.navigate('/capabilities?tab=toolsets')} variant="ghost">
          配置生图与视觉模型
        </Button>
      </div>
      {job?.selection && (
        <p className="text-xs text-muted-foreground">
          生图配置：{job.selection.provider} / {job.selection.model}
        </p>
      )}
      {job?.previous && !running && (
        <Button
          disabled={busy}
          onClick={() =>
            void act(async () =>
              setJob(
                await ctx.rest<VisualSet>(`/visual-sets/${encodeURIComponent(job.id)}/restore`, { method: 'POST' })
              )
            )
          }
          variant="outline"
        >
          恢复上一套组图（不重新生图）
        </Button>
      )}
      {job && (
        <p role="status">
          {job.detail} · 生图调用 {job.attempts.length} 次（费用以提供方回执为准）
        </p>
      )}
      {job?.review && (
        <div className="text-sm">
          <p>
            {job.review.pass === true ? '视觉检查通过，仍需人工审核' : '视觉检查待处理'}：{job.review.reason}
          </p>
          {job.review.issues?.map((issue, index) => (
            <p key={index}>{String(issue)}</p>
          ))}
        </div>
      )}
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <div className={compact ? 'grid gap-4' : 'grid gap-4 sm:grid-cols-2 xl:grid-cols-3'}>
        {job?.pages.map((page, index) => (
          <article className="space-y-2" key={page.asset_id}>
            <p className="text-sm">
              {index + 1}. {page.title}
            </p>
            <AssetImage ctx={ctx} id={page.asset_id} />
            <ExpandedImage ctx={ctx} id={page.asset_id} />
            {page.has_art && job.state === 'completed' && (
              <Button
                disabled={busy || running || job.attempts.length >= 3}
                onClick={() => void generate(true, index)}
                size="sm"
                variant="outline"
              >
                重做此页主视觉（1 次生图）
              </Button>
            )}
          </article>
        ))}
      </div>
      {job?.state === 'completed' && (
        <Button
          disabled={busy}
          onClick={() =>
            void act(async () => {
              await apply(job.id)
              setNotice('组图已应用，尚未审核或发布。')
            })
          }
        >
          应用整套组图（替换当前配图）
        </Button>
      )}
      <p className="text-xs text-muted-foreground">
        生成失败会保留文字和已完成页面；修改稿件后需重新核对组图。保存草稿不会触发生图。
      </p>
    </section>
  )
}

interface ImageProps {
  ctx: PluginContext
  id: string
}

function ExpandedImage(props: ImageProps) {
  const [open, setOpen] = useState(false)

  return (
    <details onToggle={event => setOpen(event.currentTarget.open)}>
      <summary className="cursor-pointer text-xs">查看原图</summary>
      {open && <FullImage {...props} />}
    </details>
  )
}

function FullImage({ ctx, id }: ImageProps) {
  const [image, setImage] = useState(''),
    [error, setError] = useState('')

  useEffect(() => {
    let live = true
    void ctx
      .rest<{ data: string; mime?: string }>(`/assets/${id}`)
      .then(value => {
        if (live) {
          setImage(`data:${value.mime || 'image/png'};base64,${value.data}`)
        }
      })
      .catch(reason => {
        if (live) {
          setError(String(reason))
        }
      })

    return () => {
      live = false
    }
  }, [ctx, id])

  return image ? <img alt="完整组图页面" className="w-full" src={image} /> : <p>{error || '正在加载原图…'}</p>
}
