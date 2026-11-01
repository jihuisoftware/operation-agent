import { Badge, Button, Checkbox } from '@hermes/plugin-sdk'
import { useState } from 'react'

import type { AnalysisApi, AnalysisCatalog, Dataset, Sharing, Template } from './analysis-types'
import { BusinessImport } from './business-import'
import { BusinessSharing } from './business-sharing'

function DatasetPermissions({ dataset, template, api, saved }: { dataset: Dataset; template: Template; api: AnalysisApi; saved: () => void }) {
  const [sharing, setSharing] = useState<Sharing>(dataset.sharing)
  const [active, setActive] = useState(dataset.active)
  const [preview, setPreview] = useState<{ preview_token: string; model_sample: unknown[] } | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const update = async (save: boolean) => {
    setBusy(true); setError('')

    try {
      const body = { ...sharing, active, version: dataset.version }

      if (save && preview) { await api(`/datasets/${dataset.id}`, { ...body, preview_token: preview.preview_token }); saved() }
      else { setPreview(await api(`/datasets/${dataset.id}/preview`, body)) }
    } catch (reason) { setError(String(reason)) }
    finally { setBusy(false) }
  }

  return <div className="space-y-4">
    <label className="flex items-center gap-2"><Checkbox checked={active} onCheckedChange={v => { setActive(v === true); setPreview(null) }} />纳入后续分析</label>
    <BusinessSharing onChange={value => { setSharing(value); setPreview(null) }} template={template} value={sharing} />
    {error && <p className="text-destructive" role="alert">{error}</p>}
    <Button disabled={busy} onClick={() => void update(false)} variant="outline">预览使用选项</Button>
    {preview && <><pre className="overflow-auto text-xs">{JSON.stringify(preview.model_sample, null, 2)}</pre><Button disabled={busy} onClick={() => void update(true)}>确认并保存权限</Button></>}
  </div>
}

export function BusinessDatasets({ data, api, saved }: { data: AnalysisCatalog; api: AnalysisApi; saved: () => void }) {
  return <div className="space-y-6">
    <BusinessImport api={api} saved={saved} templates={data.templates} />
    <h3 className="font-medium">已保存的数据集</h3>
    {!data.datasets.length && <p className="text-muted-foreground">还没有业务数据。可先使用已采集资料完成分析。</p>}
    {data.datasets.map(dataset => <article className="space-y-3 border-t pt-4" key={`${dataset.id}:${dataset.version}`}>
      <h4 className="flex items-center gap-2 font-medium">{dataset.name}<Badge>{dataset.active ? '使用中' : '已停用'}</Badge><Badge>{dataset.sharing.public_metrics.length ? '部分汇总可公开' : '仅内部'}</Badge></h4>
      <p className="text-xs text-muted-foreground">{dataset.scope_topic} · 版本 {dataset.version} · {dataset.batches.length} 个有效批次 · {dataset.config.definition}</p>
      <details className="space-y-4"><summary className="cursor-pointer">模型与公开权限</summary><DatasetPermissions api={api} dataset={dataset} saved={saved} template={data.templates[dataset.config.template]} /></details>
      <details className="space-y-4"><summary className="cursor-pointer">追加或替换数据</summary><BusinessImport api={api} dataset={dataset} saved={saved} templates={data.templates} /></details>
    </article>)}
    <details><summary className="cursor-pointer">导入记录与错误</summary>{data.batches.map(batch => <div className="my-3 text-xs" key={batch.id}><p>{batch.id} · 保存 {batch.inserted} · 重复 {batch.duplicates} · 无效 {batch.invalid}</p>{batch.errors.map(e => <p key={e.row}>第 {e.row} 行：{e.error}</p>)}</div>)}</details>
  </div>
}
