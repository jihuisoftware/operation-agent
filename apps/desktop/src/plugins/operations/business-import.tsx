import { Button, Checkbox, Input } from '@hermes/plugin-sdk'
import { useState } from 'react'

import type { AnalysisApi, BusinessConfig, Dataset, Sharing, Template } from './analysis-types'
import { BusinessSharing, defaultSharing } from './business-sharing'
import { ChoiceField, choices } from './configuration-choices'

interface Upload { upload_id: string; sheet: string; sheets: string[]; headers: string[]; sample: Record<string, string>[]; suggestions: Record<string, Record<string, string>> }
interface Preview { valid: number; invalid: number; errors: { row: number; error: string }[]; model_sample: unknown[]; sample: unknown[]; preview_token: string }

async function fileBase64(file: File) {
  if (file.size > 20 * 1024 * 1024) { throw new Error('文件不能超过 20 MB') }

  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1])
    reader.onerror = () => reject(new Error('文件读取失败'))
    reader.readAsDataURL(file)
  })
}

export function BusinessImport({ api, templates, dataset, saved }: { api: AnalysisApi; templates: Record<string, Template>; dataset?: Dataset; saved: () => void }) {
  const [upload, setUpload] = useState<Upload | null>(null)
  const [config, setConfig] = useState<BusinessConfig>(dataset?.config || { template: 'sales', mapping: {}, date_format: '%Y-%m-%d', semantics: 'increment', currency: 'CNY', definition: '', dedupe: false })
  const [sharing, setSharing] = useState<Sharing>(dataset?.sharing || defaultSharing)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [exclude, setExclude] = useState(false)
  const [replace, setReplace] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const change = (next: BusinessConfig) => { setConfig(next); setPreview(null) }
  const body = () => ({ ...config, ...sharing, upload_id: upload?.upload_id, sheet: upload?.sheet, dataset_id: dataset?.id, dataset_version: dataset?.version, replace })

  const act = async (fn: () => Promise<void>) => {
    setBusy(true); setError('')

    try { await fn() } catch (reason) { setError(String(reason)) } finally { setBusy(false) }
  }

  const selectFile = async (file: File) => {
    const value = await api<Upload>('/upload', { name: file.name, data: await fileBase64(file) })
    setUpload(value); setPreview(null)

    if (!dataset) { setConfig({ ...config, mapping: value.suggestions[config.template] }) }
  }

  return <section aria-label="导入业务数据" className="space-y-5">
    <h3 className="font-medium">{dataset ? `导入到 ${dataset.name}` : '导入业务数据'} · 文件 → 字段匹配 → 检查并保存</h3>
    {error && <p className="text-destructive" role="alert">{error}</p>}
    <label className="grid gap-2">选择 CSV / Excel<Input accept=".csv,.xlsx" disabled={busy} onChange={e => { const file = e.target.files?.[0];

        if (file) { void act(() => selectFile(file)) } }} type="file" /></label>
    <p className="text-xs text-muted-foreground">最多 20 MB、10 万行；CSV 使用 UTF-8 编码，Excel 公式需已有数值缓存。</p>
    {upload && <>
      <ChoiceField allowCustom={false} allowEmpty={false} label="工作表" onChange={sheet => void act(async () => { const next = await api<Upload>('/sheet', { upload_id: upload.upload_id, sheet }); setUpload({ ...next, sheets: upload.sheets }); setPreview(null);

        if (!dataset) { setConfig({ ...config, mapping: next.suggestions[config.template] }) } })} options={choices(upload.sheets)} value={upload.sheet} />
      {!dataset && <ChoiceField allowCustom={false} allowEmpty={false} label="业务模板" onChange={template => { change({ ...config, template, mapping: upload.suggestions[template] }); setSharing(defaultSharing) }} options={Object.entries(templates).map(([value, t]) => ({ value, label: t.title }))} value={config.template} />}
      <details><summary>原始数据预览（本地）</summary><pre className="overflow-auto text-xs">{JSON.stringify(upload.sample, null, 2)}</pre></details>
      <div className="grid gap-3 md:grid-cols-3">{Object.entries(templates[config.template].fields).map(([field, label]) => <ChoiceField allowCustom={false} key={field} label={label} onChange={value => change({ ...config, mapping: { ...config.mapping, [field]: value } })} options={choices(upload.headers)} value={config.mapping[field] || ''} />)}</div>
      <div className="grid gap-3 md:grid-cols-3">
        <ChoiceField allowCustom={false} allowEmpty={false} label="日期格式" onChange={date_format => change({ ...config, date_format })} options={[{ value: '%Y-%m-%d', label: '年-月-日' }, { value: '%Y/%m/%d', label: '年/月/日' }, { value: '%Y%m%d', label: '年月日（8位）' }, { value: '%d/%m/%Y', label: '日/月/年' }, { value: '%m/%d/%Y', label: '月/日/年' }]} value={config.date_format} />
        <ChoiceField allowCustom={false} allowEmpty={false} label="金额币种" onChange={currency => change({ ...config, currency })} options={choices(['CNY', 'USD', 'EUR', 'JPY', 'HKD'])} value={config.currency} />
        <ChoiceField allowCustom={false} allowEmpty={false} label="指标类型" onChange={semantics => change({ ...config, semantics })} options={[{ value: 'increment', label: '逐笔／每日增量' }, { value: 'snapshot', label: '累计快照（取最新）' }]} value={config.semantics} />
      </div>
      <label className="grid gap-2">指标口径<Input maxLength={500} onChange={e => change({ ...config, definition: e.target.value })} placeholder="例如：支付成功的订单金额，不含运费，退款另计" value={config.definition} /></label>
      <label className="flex items-center gap-2"><Checkbox checked={config.dedupe} onCheckedChange={v => change({ ...config, dedupe: v === true })} />按已映射的业务键跨批次去重</label>
      {dataset && <label className="flex items-center gap-2"><Checkbox checked={replace} onCheckedChange={v => { setReplace(v === true); setPreview(null) }} />替换当前有效批次（历史结果保留）</label>}
      <BusinessSharing onChange={value => { setSharing(value); setPreview(null) }} template={templates[config.template]} value={sharing} />
      <Button disabled={busy} onClick={() => void act(async () => setPreview(await api<Preview>('/preview', body())))} variant="outline">校验与发送范围预览</Button>
      {preview && <div className="space-y-3">
        <p>有效 {preview.valid} 行 · 无效 {preview.invalid} 行</p>
        <details open={preview.invalid > 0}><summary>校验问题（最多展示前 100 条）</summary>{preview.errors.map(e => <p key={e.row}>第 {e.row} 行：{e.error}</p>)}</details>
        <details><summary>规范化数据预览</summary><pre className="overflow-auto text-xs">{JSON.stringify(preview.sample, null, 2)}</pre></details>
        <details open><summary>模型明细预览（前 20 行）；汇总模式仅发送计算后的指标</summary><pre className="overflow-auto text-xs">{JSON.stringify(preview.model_sample, null, 2)}</pre></details>
        {preview.invalid > 0 && <label className="flex items-center gap-2"><Checkbox checked={exclude} onCheckedChange={v => setExclude(v === true)} />排除无效行后导入</label>}
        <Button disabled={busy || !preview.valid || (preview.invalid > 0 && !exclude)} onClick={() => void act(async () => { await api('/confirm', { ...body(), preview_token: preview.preview_token, exclude_invalid: exclude, request_id: crypto.randomUUID() }); setUpload(null); setPreview(null); saved() })}>确认使用选项并保存</Button>
      </div>}
    </>}
  </section>
}
