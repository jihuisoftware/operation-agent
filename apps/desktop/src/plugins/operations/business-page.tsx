import type { PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useMemo, useState } from 'react'

import type { AnalysisApi, AnalysisCatalog } from './analysis-types'
import { BusinessDatasets } from './business-datasets'
import { NewRecord } from './workbench-widgets'

export function BusinessPage({ ctx }: { ctx: PluginContext }) {
  const [data, setData] = useState<AnalysisCatalog | null>(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)

  const api = useMemo<AnalysisApi>(
    () => (path, body) => ctx.rest(`/analysis${path}`, { method: body ? 'POST' : 'GET', body }),
    [ctx]
  )

  useEffect(() => {
    let active = true
    void api<AnalysisCatalog>('')
      .then(value => {
        if (active) {
          setData(value)
        }
      })
      .catch(reason => {
        if (active) {
          setError(String(reason))
        }
      })

    return () => {
      active = false
    }
  }, [api, revision])

  return (
    <section className="p-4">
      {error && <p role="alert">{error}</p>}
      {data ? (
        <BusinessDatasets api={api} data={data} saved={() => setRevision(value => value + 1)} />
      ) : (
        !error && <p>正在读取业务数据…</p>
      )}
      <details className="mt-4">
        <summary className="cursor-pointer">指标 JSON 导入</summary>
        <NewRecord ctx={ctx} kind="metric" onError={setError} onSaved={async () => setRevision(value => value + 1)} />
      </details>
    </section>
  )
}
