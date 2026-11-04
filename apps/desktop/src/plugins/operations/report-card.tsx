import { Button, CopyButton, formatTimestampMinute, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import type { RecordRow } from './types'
import { download } from './workbench-widgets'

interface ReportCardProps {
  ctx: PluginContext
  row: RecordRow
}

export function ReportCard({ ctx, row }: ReportCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [details, setDetails] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    let disposed = false
    setDetails('')
    setError('')

    if (expanded) {
      void ctx.rest<{ markdown: string }>(`/reports/${encodeURIComponent(row.id)}/details`).then(value => {
        if (!disposed) { setDetails(value.markdown) }
      }).catch(reason => {
        if (!disposed) { setError(String(reason)) }
      })
    }

    return () => { disposed = true }
  }, [ctx, row.id, expanded])

  return (
    <details>
      <summary className="cursor-pointer">{String(row.day)} 日报 · {formatTimestampMinute(String(row.created))}</summary>
      <div className="flex gap-2">
        <CopyButton label="复制日报" text={String(row.markdown)} />
        <Button onClick={() => download(String(row.day), String(row.markdown))} variant="outline">导出 Markdown</Button>
        {Boolean(row.details_id) && <Button onClick={() => setExpanded(value => !value)} variant="outline">{expanded ? '收起完整详情' : '查看完整详情'}</Button>}
      </div>
      <pre className="whitespace-pre-wrap break-words">{String(row.markdown)}</pre>
      {expanded && <div>
        {error && <p role="alert">{error}</p>}
        {!details && !error && <p role="status">正在加载完整详情…</p>}
        {details && <>
          <div className="flex gap-2">
            <CopyButton label="复制完整详情" text={details} />
            <Button onClick={() => download(`${String(row.day)}-完整详情`, details)} variant="outline">导出完整详情</Button>
          </div>
          <pre className="whitespace-pre-wrap break-words">{details}</pre>
        </>}
      </div>}
    </details>
  )
}
