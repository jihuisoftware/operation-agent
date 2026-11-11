import { Button, host, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import { coverAssetIds, versionRequest } from './content-version-actions'
import type { RecordRow } from './types'

interface CoverSpec { title: string; subtitle: string; eyebrow: string; keywords: string[]; template: string; palette: string; size: string }
interface Candidate { asset_id: string; cover: CoverSpec; template_label: string; palette_label: string }
interface Options { templates: { id: string; label: string }[]; palettes: { id: string; label: string; color: string }[] }
interface Preview extends Options { set_id: string; candidates: Candidate[] }
interface Props { ctx: PluginContext; row: RecordRow; refresh: () => Promise<unknown>; working?: { preview: (spec: CoverSpec) => Promise<Preview>; apply: (id: string) => Promise<void> } }

function initialSpec(row: RecordRow): CoverSpec {
  return { title: String(row.title || ''), subtitle: '', eyebrow: '主题分享', keywords: [], template: 'editorial', palette: 'blue', size: 'normal', ...(row.cover as Partial<CoverSpec> || {}) }
}

function firstAsset(row: RecordRow) { return String((row.asset_ids as string[] || [])[0] || '') }

function CoverArt({ ctx, item, large = false }: { ctx: PluginContext; item: Candidate; large?: boolean }) {
  const [image, setImage] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    let disposed = false
    setImage(''); setError('')
    void ctx.rest<{ data: string; mime?: string }>(`/assets/${encodeURIComponent(item.asset_id)}${large ? '' : '?thumbnail=true'}`).then(value => {
      if (!disposed) { setImage(`data:${value.mime || 'image/png'};base64,${value.data}`) }
    }).catch(reason => { if (!disposed) { setError(String(reason)) } })

    return () => { disposed = true }
  }, [ctx, item.asset_id, large])

  return error ? <p role="alert">{error}</p> : image ? <img alt={`${item.template_label}封面预览`} className={large ? 'mx-auto max-h-[70vh] max-w-full object-contain' : 'aspect-[3/4] w-full rounded object-contain'} src={image} /> : <p>正在读取封面…</p>
}

function Choices({ ctx, items, selected, onSelect, disabled }: { ctx: PluginContext; items: Candidate[]; selected: string; onSelect: (item: Candidate) => void; disabled: boolean }) {
  return <div className="grid gap-3 sm:grid-cols-3">{items.map(item => <article className={`space-y-2 rounded-xl border p-3 ${selected === item.asset_id ? 'ring-2 ring-primary' : ''}`} key={item.asset_id}>
    <CoverArt ctx={ctx} item={item} />
    <p className="text-sm">{item.template_label} · {item.palette_label}</p>
    <Button aria-pressed={selected === item.asset_id} disabled={disabled} onClick={() => onSelect(item)} size="sm" variant="outline">选用{item.template_label}</Button>
  </article>)}</div>
}

export function CoverStudio({ ctx, row, refresh, working }: Props) {
  const [spec, setSpec] = useState<CoverSpec>(() => initialSpec(row))
  const [words, setWords] = useState(spec.keywords.join('、'))
  const [options, setOptions] = useState<Options | null>(null)
  const [items, setItems] = useState<Candidate[]>((row.cover_candidates || []) as Candidate[])
  const [selected, setSelected] = useState(firstAsset(row))
  const [setId, setSetId] = useState('')
  const [rendered, setRendered] = useState(JSON.stringify(spec))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [savedId, setSavedId] = useState('')
  const [large, setLarge] = useState(false)
  const release = row.release as { state?: string } | undefined
  useEffect(() => {
    let disposed = false
    void ctx.rest<Options>('/content/cover-options').then(value => { if (!disposed) { setOptions(value) } })
      .catch(reason => { if (!disposed) { setError(String(reason)) } })

    return () => { disposed = true }
  }, [ctx])
  const draft = { ...spec, keywords: words.split(/[,，、]/).map(word => word.trim()).filter(Boolean) }
  const dirty = JSON.stringify(draft) !== rendered
  const choice = options ? items.find(item => item.asset_id === selected) : undefined

  const preview = async () => {
    setBusy(true); setError(''); setNotice('')

    try {
      const result = working ? await working.preview(draft) : await ctx.rest<Preview>(`/content/${row.id}/covers/preview`, { method: 'POST', timeoutMs: 60000,
        body: { version: row.policy_version, content_revision: row.content_revision, cover: draft } })

      setOptions(result); setItems(result.candidates); setSetId(result.set_id)
      const first = result.candidates[0]
      setSelected(first.asset_id); setSpec(first.cover); setWords(first.cover.keywords.join('、')); setRendered(JSON.stringify(first.cover))
      setNotice('三个候选已就绪。本地排版，不调用模型；请同时检查大图和小图。')
    } catch (reason) { setError(String(reason)) } finally { setBusy(false) }
  }

  const save = async () => {
    if (!choice || dirty) { return }
    setBusy(true); setError('')

    try {
      if (working) { await working.apply(choice.asset_id); setNotice('封面已保存到写作草稿，尚未提交审核');

 return }

      const assetIds = coverAssetIds(row, choice.asset_id)

      const result = await ctx.rest<{ id: string; original_schedule_retained: boolean }>(`/content/${row.id}/versions`, { method: 'POST',
        body: versionRequest(row, { asset_ids: assetIds, ...(setId ? { cover_set_id: setId } : {}) }) })

      setSavedId(result.id)
      setNotice('封面已更新到原内容，原审核与排期已失效；请重新审核后安排发布。')
      await refresh()
    } catch (reason) { setError(String(reason)) } finally { setBusy(false) }
  }

  return <section aria-label="封面设计" className="space-y-4 rounded-xl bg-muted/30 p-4">
    <p className="text-sm text-muted-foreground">封面标题独立于文章标题。修改文字、配色和布局只在本地绘制，不消耗模型额度。</p>
    <p className="text-xs text-muted-foreground">主标题建议 8–18 字；副标题说明内容，关键词突出阅读重点。旧稿也可先补全文案，再生成候选。</p>
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="grid gap-1 text-sm">封面主标题<textarea aria-label="封面主标题" className="rounded border bg-background p-2" disabled={busy} maxLength={36} onChange={event => setSpec({ ...spec, title: event.target.value })} rows={2} value={spec.title} /></label>
      <label className="grid gap-1 text-sm">副标题<input aria-label="封面副标题" className="rounded border bg-background p-2" disabled={busy} maxLength={60} onChange={event => setSpec({ ...spec, subtitle: event.target.value })} value={spec.subtitle} /></label>
      <label className="grid gap-1 text-sm">栏目标签<input aria-label="封面栏目" className="rounded border bg-background p-2" disabled={busy} maxLength={12} onChange={event => setSpec({ ...spec, eyebrow: event.target.value })} value={spec.eyebrow} /></label>
      <label className="grid gap-1 text-sm">关键词（最多三项，以顿号分隔）<input aria-label="封面关键词" className="rounded border bg-background p-2" disabled={busy} onChange={event => setWords(event.target.value)} value={words} /></label>
      {options && <>
        <label className="grid gap-1 text-sm">版式<select aria-label="封面版式" className="rounded border bg-background p-2" disabled={busy} onChange={event => setSpec({ ...spec, template: event.target.value })} value={spec.template}>{options.templates.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        <label className="grid gap-1 text-sm">配色<select aria-label="封面配色" className="rounded border bg-background p-2" disabled={busy} onChange={event => setSpec({ ...spec, palette: event.target.value })} value={spec.palette}>{options.palettes.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
      </>}
      <label className="grid gap-1 text-sm">标题字号<select aria-label="标题字号" className="rounded border bg-background p-2" disabled={busy} onChange={event => setSpec({ ...spec, size: event.target.value })} value={spec.size}><option value="normal">标准（自动适配）</option><option value="large">醒目（自动适配）</option></select></label>
    </div>
    <Button disabled={busy || !options || !spec.title.trim()} onClick={() => void preview()}>{busy ? '正在处理…' : '生成三个候选封面'}</Button>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <Choices ctx={ctx} disabled={busy || dirty} items={items} onSelect={item => {
      setSelected(item.asset_id); setSpec(item.cover); setWords(item.cover.keywords.join('、')); setRendered(JSON.stringify(item.cover))
    }} selected={selected} />
    {dirty && <p className="text-sm">文字或样式已修改，请重新生成候选后再应用。</p>}
    {choice && <><Button onClick={() => setLarge(value => !value)} variant="outline">{large ? '收起大图' : '查看大图'}</Button>{large && <CoverArt ctx={ctx} item={choice} large />}</>}
    {release?.state === 'scheduled' && <p className="text-sm">应用封面会更新原内容并取消当前排期，请重新审核后设置发布时间。</p>}
    <Button disabled={busy || dirty || !choice || selected === firstAsset(row)} onClick={() => void save()}>{working ? '应用到写作草稿' : '应用封面并保存'}</Button>
    {savedId && <Button onClick={() => host.navigate(`/content?tab=drafts&record=${encodeURIComponent(savedId)}`)} variant="link">查看内容</Button>}
  </section>
}
