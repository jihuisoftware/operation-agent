import { Button, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'

interface ReviewPolicy {
  mode: 'manual' | 'automatic' | 'score'
  threshold: number
  revision: number
}
export function ReviewPolicySettings({ ctx, onDirty }: { ctx: PluginContext; onDirty?: (dirty: boolean) => void }) {
  const [value, setValue] = useState<ReviewPolicy | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const generation = useRef(0)
  useEffect(() => {
    let active = true
    generation.current += 1
    setValue(null)
    setError('')
    setBusy(false)
    ctx.rest<ReviewPolicy>('/review-policy').then(
      data => {
        if (active) {
          setValue(data)
        }
      },
      e => {
        if (active) {
          setError(String(e))
        }
      }
    )
    return () => {
      active = false
      generation.current += 1
    }
  }, [ctx])
  const save = async () => {
    if (!value) {
      return
    }
    const epoch = generation.current
    setBusy(true)
    setError('')
    try {
      const result = await ctx.rest<ReviewPolicy>('/review-policy', {
        method: 'PUT',
        body: { mode: value.mode, threshold: value.threshold, expected_revision: value.revision }
      })
      if (epoch === generation.current) {
        setValue(result)
        onDirty?.(false)
      }
    } catch (e) {
      if (epoch === generation.current) {
        setError(String(e))
      }
    } finally {
      if (epoch === generation.current) {
        setBusy(false)
      }
    }
  }
  return (
    <section aria-label="内容审核策略" className="space-y-3 rounded border p-3">
      <h3 className="font-medium">内容审核策略</h3>
      <p className="text-sm text-muted-foreground">
        独立保存，仅适用于后续 AI 新稿。手写稿仍需人工审核，历史稿件需逐篇复检。自动通过后进入下一个发布时段。
      </p>
      {value && (
        <>
          <label className="grid gap-1">
            审核模式
            <select
              aria-label="审核模式"
              className="rounded border bg-background p-2"
              value={value.mode}
              disabled={busy}
              onChange={e => { onDirty?.(true); setValue({ ...value, mode: e.target.value as ReviewPolicy['mode'] }) }}
            >
              <option value="manual">始终人工审核</option>
              <option value="automatic">自动检查通过后放行</option>
              <option value="score">按评分分流</option>
            </select>
          </label>
          {value.mode === 'score' && (
            <label className="grid gap-1">
              自动放行门槛（正文与图片分别达标）
              <input
                aria-label="自动放行门槛"
                type="number"
                min={0}
                max={100}
                value={value.threshold}
                disabled={busy}
                onChange={e => { onDirty?.(true); setValue({ ...value, threshold: Number(e.target.value) }) }}
              />
            </label>
          )}
          <p className="text-xs">自动放行会授权发布。更改策略会使未提交的自动排期失效；不会改变人工排期。</p>
          <Button
            disabled={busy || !Number.isInteger(value.threshold) || value.threshold < 0 || value.threshold > 100}
            onClick={() => void save()}
          >
            保存审核策略
          </Button>
        </>
      )}
      {error && <p role="alert">{error} 请重新打开设置读取最新策略。</p>}
    </section>
  )
}

interface Decision {
  approved: boolean
  mode: string
  reason: string
  threshold: number
  scores: { text: number | null; visual: number | null }
}
export function ContentReviewDecision({
  row,
  ctx,
  refresh
}: {
  row: Record<string, any>
  ctx: PluginContext
  refresh: () => Promise<unknown>
}) {
  const decision = row.automatic_review as Decision | undefined
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const recheck = async () => {
    setBusy(true)
    setError('')
    try {
      await ctx.rest(`/content/${row.id}/recheck-review`, {
        method: 'POST',
        timeoutMs: 900_000,
        body: { request_id: crypto.randomUUID(), content_revision: row.content_revision }
      })
      await refresh()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }
  const manual = async () => {
    setBusy(true)
    setError('')
    try {
      await ctx.rest(`/content/${row.id}/manual-review`, {
        method: 'POST',
        body: { content_revision: row.content_revision, expected_revision: row.release?.revision }
      })
      await refresh()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="space-y-2" aria-label="自动审核结果">
      {decision && (
        <>
          <p>{row.release?.state === 'scheduled' ? '审核已通过，等待排期执行' : decision.reason}</p>
          <p>审核方式：{({ manual: '人工审核', automatic: '检查通过自动放行', score: '按评分分流' } as Record<string, string>)[decision.mode]}</p>
          <p>
            正文评分：{decision.scores.text ?? '不可用'} · 图片评分：{decision.scores.visual ?? '不可用'}
            {decision.mode === 'score' && ` · 门槛：${decision.threshold}`}
          </p>
          <p className="text-xs text-muted-foreground">分数是质量评价，不是事实正确概率。</p>
        </>
      )}
      {decision?.approved && !row.publication_state && (
        <Button disabled={busy} variant="outline" onClick={() => void manual()}>
          转人工审核
        </Button>
      )}
      {!row.manual && !row.publication_state && (!row.release || row.release.state === 'cancelled') && (
        <Button disabled={busy} variant="outline" onClick={() => void recheck()}>
          {busy ? '正在检查…' : '重新检查并应用当前策略'}
        </Button>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  )
}
