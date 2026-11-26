import { Button, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'

import { versionRequest } from './content-version-actions'
import type { RecordRow } from './types'

interface Draft extends RecordRow {
  asset_ids: string[]
  release?: { state: string; revision?: number } | null
}

function needsCover(row: Draft) {
  return Array.isArray(row.asset_ids) && row.asset_ids.length === 0 && !row.publication_state &&
    (!row.release || row.release.state === 'cancelled')
}

export function GenerateCoversButton({ ctx, record, refresh }: {
  ctx: PluginContext; record: string; refresh: () => Promise<unknown>
}) {
  const active = useRef<AbortController | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')

  useEffect(() => {
    setBusy(false)
    setNotice('')

    return () => active.current?.abort()
  }, [ctx, record])

  const generate = async () => {
    if (active.current && !active.current.signal.aborted) { return }
    const run = new AbortController()
    active.current = run
    setBusy(true)
    setNotice('')
    let generated = 0
    const errors: string[] = []

    try {
      let before = '0'

      do {
        const query = new URLSearchParams({ filter: 'drafts', compact: 'true', before, record })
        const page = await ctx.rest<{ content: Draft[]; next?: string }>(`/library/content?${query}`)

        for (const row of page.content.filter(needsCover)) {
          if (run.signal.aborted) { return }

          try {
            const path = `/content/${encodeURIComponent(row.id)}`
            const { content } = await ctx.rest<{ content: Draft }>(`${path}/details`)

            if (run.signal.aborted) { return }

            if (!needsCover(content)) { continue }
            await ctx.rest(`${path}/generate-cover`, { method: 'POST', body: versionRequest(content, {
              expected_release_revision: content.release?.revision ?? 0
            }), timeoutMs: 900_000 })
            generated++
          } catch (reason) { errors.push(`${row.title || '未命名图文'}：${String(reason)}`) }
        }

        before = page.next || ''
      } while (before && !record && !run.signal.aborted)
    } catch (reason) { errors.push(String(reason)) }
    finally {
      if (!run.signal.aborted) {
        active.current = null
        setBusy(false)
        const result = generated || errors.length ? `已为 ${generated} 篇待审核稿件生成封面。` : '待审核稿件均无需补封面。'
        setNotice(errors.length ? `${result}失败 ${errors.length} 项。\n${errors.join('\n')}` : result)

        if (generated) { await refresh() }
      }
    }
  }

  return <>
    {notice && <p className="whitespace-pre-line text-sm" role="status">{notice}</p>}
    <Button disabled={busy} onClick={() => void generate()} variant="outline">{busy ? '正在生成封面…' : '一键生成封面'}</Button>
  </>
}
