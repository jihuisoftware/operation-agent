import { useEffect, useState } from 'react'

import { hermesApiAs, resolveOwnerNow } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Codicon } from '@/components/ui/codicon'
import { CopyButton } from '@/components/ui/copy-button'
import { useI18n } from '@/i18n'
import type { SessionInfo } from '@/types/hermes'

import { isCronRunRow, openCronRun } from './open-cron-run'

interface RunRecordProps {
  jobId: string
  run: SessionInfo
  time: string
  onOpenSession?: (sessionId: string, session?: SessionInfo) => void
}

export function RunRecord({ jobId, run, time, onOpenSession }: RunRecordProps) {
  const { t } = useI18n()
  const [expanded, setExpanded] = useState(false)
  const [output, setOutput] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  const [owner] = useState(() => resolveOwnerNow({ connectionId: run.connection_id, profile: run.profile }))
  const title = run.title?.trim() || run.preview?.trim() || run.id
  const fallback = run.preview?.trim() || title
  const text = run.output_file ? output : fallback

  useEffect(() => {
    if (!expanded || !run.output_file || output !== null) {return}
    let cancelled = false
    setError('')
    void hermesApiAs<{ output: string }>(owner, {
      path: `/api/cron/jobs/${encodeURIComponent(jobId)}/output?filename=${encodeURIComponent(run.output_file)}`
    }).then(result => {
      if (!cancelled) {setOutput(result.output)}
    }).catch(reason => {
      if (!cancelled) {setError(String(reason))}
    })

    return () => { cancelled = true }
  }, [expanded, jobId, output, owner, retry, run.output_file])

  return (
    <div className="text-xs">
      <button
        aria-expanded={expanded}
        className="row-hover flex w-full items-center gap-2 rounded-md px-2 py-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
        onClick={() => setExpanded(value => !value)}
        type="button"
      >
        <Codicon name={expanded ? 'chevron-down' : 'chevron-right'} size="0.75rem" />
        <span className="min-w-0 flex-1 truncate text-foreground/85">{title}</span>
        <span className="shrink-0 text-muted-foreground/55 tabular-nums">{time}</span>
      </button>
      {expanded && (
        <div aria-label={t.cron.fullRunOutput} className="space-y-2 px-2 py-2" role="region">
          <div className="flex items-center gap-2">
            <CopyButton disabled={text === null} showLabel text={text ?? ''} />
            {isCronRunRow(run) && onOpenSession && (
              <Button onClick={() => openCronRun(run, onOpenSession)} size="sm" variant="ghost">
                {t.cron.openRunSession}
              </Button>
            )}
          </div>
          {error ? (
            <div role="alert">
              <p className="select-text whitespace-pre-wrap break-words text-destructive">{error}</p>
              <Button onClick={() => setRetry(value => value + 1)} size="sm" variant="ghost">{t.common.retry}</Button>
            </div>
          ) : text === null ? (
            <p className="text-muted-foreground">{t.cron.loading}</p>
          ) : (
            <>
              {!run.output_file && <p className="text-muted-foreground">{t.cron.outputUnavailable}</p>}
              <pre className="max-h-96 select-text overflow-auto whitespace-pre-wrap break-words font-mono text-xs">{text}</pre>
            </>
          )}
        </div>
      )}
    </div>
  )
}
