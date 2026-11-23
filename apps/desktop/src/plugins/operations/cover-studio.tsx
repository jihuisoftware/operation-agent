import { Button, host, type PluginContext } from '@hermes/plugin-sdk'
import { useCallback, useEffect, useState } from 'react'

import { coverAssetIds, versionRequest } from './content-version-actions'
import type { RecordRow } from './types'

interface CoverSpec { title: string; subtitle: string; eyebrow: string; keywords: string[]; template: string; palette: string; size: string; style?: string; variant?: string }
interface Candidate { asset_id: string; cover: CoverSpec; template_label: string; palette_label: string; variant_label?: string }
interface CartoonPose { id: string; label: string; group?: string }
interface Options { cartoon_characters?: CartoonPose[]; social_styles?: { id: string; label: string }[]; templates: { id: string; label: string }[]; palettes: { id: string; label: string; color: string }[] }
interface Preview extends Options { set_id: string; candidates: Candidate[] }
interface Props { ctx: PluginContext; row: RecordRow; refresh: () => Promise<unknown>; working?: { preview: (spec: CoverSpec) => Promise<Preview>; apply: (id: string) => Promise<void> } }

function initialSpec(row: RecordRow): CoverSpec {
  const saved = row.cover as Partial<CoverSpec> | undefined
  return { title: String(row.title || ''), subtitle: '', keywords: [], template: 'editorial', palette: 'blue', size: 'normal', ...saved, eyebrow: saved?.eyebrow === '主题分享' ? '' : saved?.eyebrow || '' }
}

function firstAsset(row: RecordRow) { return String((row.asset_ids as string[] || [])[0] || '') }

interface CoverArtProps {
  ctx: PluginContext
  item: Candidate
  onUnavailable: (id: string) => void
  large?: boolean
}

function CoverArt({ ctx, item, onUnavailable, large = false }: CoverArtProps) {
  const [image, setImage] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    let disposed = false
    setImage(''); setError('')
    void ctx.rest<{ data: string; mime?: string }>(`/assets/${encodeURIComponent(item.asset_id)}${large ? '' : '?thumbnail=true'}`).then(value => {
      if (!disposed) { setImage(`data:${value.mime || 'image/png'};base64,${value.data}`) }
    }).catch(reason => {
      if (disposed) { return }
      const message = String(reason)

      if (message.includes('素材不存在或已撤回')) {
        onUnavailable(item.asset_id)
      } else {
        setError(message)
      }
    })

    return () => { disposed = true }
  }, [ctx, item.asset_id, large, onUnavailable])

  return error ? <p role="alert">{error}</p> : image ? <img alt={`${item.template_label}封面预览`} className={large ? 'mx-auto max-h-[70vh] max-w-full object-contain' : 'aspect-[3/4] w-full rounded object-contain'} src={image} /> : <p>正在读取封面…</p>
}

interface ChoicesProps {
  ctx: PluginContext
  items: Candidate[]
  selected: string
  onSelect: (item: Candidate) => void
  onUnavailable: (id: string) => void
  disabled: boolean
}

function Choices({ ctx, items, selected, onSelect, onUnavailable, disabled }: ChoicesProps) {
  return <div className="grid gap-3 sm:grid-cols-3">{items.map(item => <article className={`space-y-2 rounded-xl border p-3 ${selected === item.asset_id ? 'ring-2 ring-primary' : ''}`} key={item.asset_id}>
    <CoverArt ctx={ctx} item={item} onUnavailable={onUnavailable} />
    <p className="text-sm">{item.template_label} · {item.palette_label}</p>
    {item.variant_label && <p className="text-xs text-muted-foreground">{item.variant_label}</p>}
    <Button aria-pressed={selected === item.asset_id} disabled={disabled} onClick={() => onSelect(item)} size="sm" variant="outline">选用{item.variant_label || item.template_label}</Button>
  </article>)}</div>
}

function nextCartoonPose(poses: CartoonPose[], items: Candidate[], spec: CoverSpec) {
  if (spec.template !== 'cartoon' || !items.length) { return undefined }
  const group = poses.find(pose => pose.id === spec.variant)?.group
  if (!group) { return undefined }
  const siblings = poses.filter(pose => pose.group === group)
  const last = items[items.length - 1].cover
  const index = siblings.findIndex(pose => pose.id === last.variant)
  if (last.template !== 'cartoon' || index < 0 || siblings.length <= items.length) { return undefined }
  return siblings[(index + 1) % siblings.length].id
}

interface CartoonSelectProps {
  poses: CartoonPose[]
  selected: string
  disabled: boolean
  onSelect: (id: string) => void
}

function CartoonSelect({ poses, selected, disabled, onSelect }: CartoonSelectProps) {
  const group = poses.find(pose => pose.id === selected)?.group
  const groups = [...new Set(poses.map(pose => pose.group).filter((name): name is string => Boolean(name)))]
  return <>
    {groups.length > 0 && <label className="grid gap-1 text-sm">角色类型
      <select className="rounded border bg-background p-2" disabled={disabled} value={group} onChange={event => {
        const first = poses.find(pose => pose.group === event.target.value)
        if (first) { onSelect(first.id) }
      }}>
        {groups.map(name => <option key={name}>{name}</option>)}
      </select>
    </label>}
    <label className="grid gap-1 text-sm">角色造型
      <select className="rounded border bg-background p-2" disabled={disabled} value={selected} onChange={event => onSelect(event.target.value)}>
        {poses.filter(pose => pose.group === group).map(pose => <option key={pose.id} value={pose.id}>{pose.label}</option>)}
      </select>
    </label>
  </>
}

interface SocialStyleProps { spec: CoverSpec; options: Options; disabled: boolean; onChange: (style: string) => void }

function SocialStyleSelect({ spec, options, disabled, onChange }: SocialStyleProps) {
  if (spec.template !== 'xiaohongshu') { return null }

  return <label className="grid gap-1 text-sm">小红书风格<select aria-label="小红书封面风格" className="rounded border bg-background p-2" disabled={disabled} onChange={event => onChange(event.target.value)} value={spec.style || 'basic'}>{options.social_styles?.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
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

  const discardUnavailable = useCallback((id: string) => {
    setItems(current => current.filter(item => item.asset_id !== id))
    setNotice('部分候选封面已失效，可选用剩余封面，或按当前设置重新生成。')
  }, [])

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

  const nextPose = dirty ? undefined : nextCartoonPose(options?.cartoon_characters || [], items, spec)
  const preview = async () => {
    const cover = nextPose ? { ...draft, variant: nextPose } : draft
    setBusy(true); setError(''); setNotice('')

    try {
      const result = working ? await working.preview(cover) : await ctx.rest<Preview>(`/content/${row.id}/covers/preview`, { method: 'POST', timeoutMs: 60000,
        body: { version: row.policy_version, content_revision: row.content_revision, cover } })

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
    <p className="text-xs text-muted-foreground">{spec.template === 'cartoon' ? '每次显示当前角色类型的三个造型，点「换一换」可按顺序循环查看。' : '优先生成同版式、同风格、同配色的不同款式；不足三个时，用其他风格补齐，配色不变。'}</p>
    <p className="text-xs text-muted-foreground">主标题建议 8–18 字；副标题说明内容，关键词突出阅读重点。旧稿也可先补全文案，再生成候选。</p>
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="grid gap-1 text-sm">封面主标题<textarea aria-label="封面主标题" className="rounded border bg-background p-2" disabled={busy} maxLength={36} onChange={event => setSpec({ ...spec, title: event.target.value })} rows={2} value={spec.title} /></label>
      <label className="grid gap-1 text-sm">副标题<input aria-label="封面副标题" className="rounded border bg-background p-2" disabled={busy} maxLength={60} onChange={event => setSpec({ ...spec, subtitle: event.target.value })} value={spec.subtitle} /></label>
      <label className="grid gap-1 text-sm">栏目标签<input aria-label="封面栏目" className="rounded border bg-background p-2" disabled={busy} maxLength={12} onChange={event => setSpec({ ...spec, eyebrow: event.target.value })} value={spec.eyebrow} /></label>
      <label className="grid gap-1 text-sm">关键词（最多三项，以顿号分隔）<input aria-label="封面关键词" className="rounded border bg-background p-2" disabled={busy} onChange={event => setWords(event.target.value)} value={words} /></label>
      {options && <>
        <label className="grid gap-1 text-sm">版式<select aria-label="封面版式" className="rounded border bg-background p-2" disabled={busy} onChange={event => setSpec({ ...spec, template: event.target.value, palette: event.target.value === 'cartoon' ? 'pink' : spec.palette, variant: undefined })} value={spec.template}>{options.templates.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
        {spec.template === 'cartoon' && <CartoonSelect poses={options.cartoon_characters || []} selected={spec.variant || 'kico'} disabled={busy} onSelect={variant => setSpec({ ...spec, variant })} />}
        <SocialStyleSelect disabled={busy} onChange={style => setSpec({ ...spec, style, variant: undefined })} options={options} spec={spec} />
        <label className="grid gap-1 text-sm">配色<select aria-label="封面配色" className="rounded border bg-background p-2" disabled={busy} onChange={event => setSpec({ ...spec, palette: event.target.value })} value={spec.palette}>{options.palettes.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
      </>}
      <label className="grid gap-1 text-sm">标题字号<select aria-label="标题字号" className="rounded border bg-background p-2" disabled={busy} onChange={event => setSpec({ ...spec, size: event.target.value })} value={spec.size}><option value="normal">标准（自动适配）</option><option value="large">醒目（自动适配）</option></select></label>
    </div>
    <Button disabled={busy || !options || !spec.title.trim()} onClick={() => void preview()}>{busy ? '正在处理…' : nextPose ? '换一换' : '生成三个候选封面'}</Button>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <Choices ctx={ctx} disabled={busy || dirty} items={items} onSelect={item => {
      setSelected(item.asset_id); setSpec(item.cover); setWords(item.cover.keywords.join('、')); setRendered(JSON.stringify(item.cover))
    }} onUnavailable={discardUnavailable} selected={selected} />
    {dirty && <p className="text-sm">文字或样式已修改，请重新生成候选后再应用。</p>}
    {choice && <><Button onClick={() => setLarge(value => !value)} variant="outline">{large ? '收起大图' : '查看大图'}</Button>{large && <CoverArt ctx={ctx} item={choice} large onUnavailable={discardUnavailable} />}</>}
    {release?.state === 'scheduled' && <p className="text-sm">应用封面会更新原内容并取消当前排期，请重新审核后设置发布时间。</p>}
    <Button disabled={busy || dirty || !choice || selected === firstAsset(row)} onClick={() => void save()}>{working ? '应用到写作草稿' : '应用封面并保存'}</Button>
    {savedId && <Button onClick={() => host.navigate(`/content?tab=drafts&record=${encodeURIComponent(savedId)}`)} variant="link">查看内容</Button>}
  </section>
}
