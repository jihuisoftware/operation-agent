import { Button, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

interface PausedRun {
  id: string
  revision: number
  error: string
  day: string
}

export function PausedRuns({ ctx }: { ctx: PluginContext }) {
  const [runs, setRuns] = useState<PausedRun[]>([])
  const [error, setError] = useState('')
  const [loadError, setLoadError] = useState('')
  const [busy, setBusy] = useState(false)
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    let disposed = false
    let loading = false

    const refresh = async () => {
      if (loading) { return }
      loading = true

      try {
        const data = await ctx.rest<{ runs: PausedRun[] }>('/runs/paused')

        if (!disposed) { setRuns(data.runs); setLoadError('') }
      } catch (reason) { if (!disposed) { setLoadError(String(reason)) } } finally { loading = false }
    }

    void refresh()
    const timer = setInterval(() => void refresh(), 2000)

    return () => { disposed = true; clearInterval(timer) }
  }, [ctx, revision])

  const resume = async (run: PausedRun) => {
    setBusy(true)
    setError('')

    try {
      await ctx.rest(`/runs/${encodeURIComponent(run.id)}/resume`, {
        method: 'POST', timeoutMs: 1_800_000,
        body: { request_id: crypto.randomUUID(), expected_revision: run.revision }
      })
      setRevision(value => value + 1)
    } catch (reason) { setError(String(reason)) } finally { setBusy(false) }
  }

  return <section aria-label="暂停的执行批次" className="space-y-2">
    {(error || loadError) && <p className="text-destructive" role="alert">{error || loadError}</p>}
    {runs.map(run => <div className="flex flex-wrap items-center gap-2" key={run.id}>
      <p>{run.day} · 已暂停：{run.error}</p>
      <Button disabled={busy} onClick={() => void resume(run)} variant="outline">检查账号并继续未完成步骤</Button>
    </div>)}
  </section>
}
