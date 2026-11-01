import { Badge, Button, Codicon, CopyButton, Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, formatTimestamp, Input, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import { CollectionSummary, type CollectionSummaryData } from './collection-summary'

interface ReferenceImage { id?: string; url: string; state: string; error?: string }
interface Source {
  id: string
  title: string
  url: string
  excerpt?: string
  text?: string
  summary?: string
  author?: string
  collected_at?: string
  published_at?: string
  scope_topic?: string
  attempts?: number
  truncated?: boolean
  original_chars?: number
  state: string
  error?: string
  images?: ReferenceImage[]
  selected: boolean
  content_versions?: { id: string; title: string; day: string }[]
}
interface Catalog { latest_collection?: CollectionSummaryData | null; version: number; topic: string; total: number; selected_count: number; items: Source[]; next_cursor: number | null }

export function ReferencePreview({ ctx, image }: { ctx: PluginContext; image?: ReferenceImage }) {
  const [url, setUrl] = useState('')
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let disposed = false
    setUrl(''); setFailed(false)

    if (image?.id) {
      void ctx.rest<{ mime: string; data: string }>(`/sources/images/${encodeURIComponent(image.id)}`)
        .then(data => { if (!disposed) { setUrl(`data:${data.mime};base64,${data.data}`) } })
        .catch(() => { if (!disposed) { setFailed(true) } })
    }

    return () => { disposed = true }
  }, [ctx, image?.id])

  return <div className="flex aspect-video items-center justify-center overflow-hidden rounded-lg bg-muted/40">
    {url && !failed ? <img alt="采集来源的参考图片" className="h-full w-full object-contain" loading="lazy" onError={() => setFailed(true)} src={url} />
      : <span className="flex items-center gap-2 text-xs text-muted-foreground"><Codicon name="file-text" />{failed || image?.state === 'unavailable' ? '图片不可用 · 正文仍可查看' : image?.id ? '正在读取图片' : '文字资料'}</span>}
  </div>
}

export function SourceLibrary({ ctx }: { ctx: PluginContext }) {
  const [data, setData] = useState<Catalog | null>(null)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [pages, setPages] = useState([0])
  const [revision, setRevision] = useState(0)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const cursor = pages[pages.length - 1]
  useEffect(() => {
    let disposed = false
    let busy = false

    const refresh = async () => {
      if (busy) { return }
      busy = true

      try {
        const result = await ctx.rest<Catalog>(`/sources?q=${encodeURIComponent(query)}&cursor=${cursor}`)

        if (!disposed) { setData(result); setError('') }
      } catch (reason) { if (!disposed) { setError(String(reason)) } }
      finally { busy = false }
    }

    setData(null)
    void refresh()
    const timer = setInterval(() => { if (!document.hidden) { void refresh() } }, 5000)

    return () => { disposed = true; clearInterval(timer) }
  }, [ctx, query, cursor, revision])

  const reuse = async (source: Source) => {
    if (!data) { return }
    setPending(true)

    try {
      await ctx.rest(`/sources/${encodeURIComponent(source.id)}/reuse`, { method: 'POST', body: { version: data.version, enabled: !source.selected } })
      setRevision(value => value + 1)
    } catch (reason) { setError(String(reason)) }
    finally { setPending(false) }
  }

  return <section aria-label="来源素材库" className="space-y-5">
    <header className="flex flex-wrap items-center justify-between gap-3"><h2 className="flex items-center gap-2 text-lg font-semibold"><Codicon name="library" />来源素材库</h2>
      <Button onClick={() => setRevision(value => value + 1)} variant="ghost">刷新素材</Button></header>
    <p className="text-sm text-muted-foreground">采集资料自动保存图文。当天同主题资料经整理归类后用于选题；历史资料可设为当前主题的长期素材，跨天复用。参考图片不等于已获发布授权。</p>
    <form className="flex gap-2" onSubmit={event => { event.preventDefault(); setQuery(search.trim()); setPages([0]) }}>
      <Input aria-label="搜索来源素材" maxLength={200} onChange={event => setSearch(event.target.value)} placeholder="按标题、正文或来源搜索" type="search" value={search} />
      <Button type="submit" variant="outline">搜索</Button>
    </form>
    {error && <p className="text-destructive" role="alert">{error}</p>}
    {data ? <>
      {data.latest_collection && <CollectionSummary data={data.latest_collection} />}
      <p className="text-xs text-muted-foreground">{data.topic || '尚未设置主题'} · 共 {data.total} 条资料 · 长期复用 {data.selected_count} 条</p>
      {!data.items.length && <p>暂无匹配的来源；信息采集完成后会自动显示。</p>}
      <div className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-4">
        {data.items.map(source => <article className="min-w-0 space-y-3 rounded-xl bg-muted/20 p-4" key={source.id}>
          <ReferencePreview ctx={ctx} image={source.images?.find(image => image.id)} />
          <div className="flex flex-wrap gap-2"><Badge variant={source.state === 'read' ? 'success' : 'muted'}>{source.state === 'read' ? '已采集' : '未取得正文'}</Badge>{source.selected && <Badge>已选复用</Badge>}</div>
          <h3 className="line-clamp-2 font-medium">{source.title}</h3>
          <p className="line-clamp-3 text-sm text-muted-foreground">{source.summary || source.excerpt || source.error || '暂无正文'}</p>
          <p className="truncate text-xs text-muted-foreground">{source.author || '作者未提供'} · {source.scope_topic || '历史资料'}</p>
          <div className="flex flex-wrap gap-2"><Button onClick={() => setSelected(source.id)} variant="outline">查看图文</Button>
            <Button disabled={pending || !data.topic || source.state !== 'read'} onClick={() => void reuse(source)} variant={source.selected ? 'secondary' : 'ghost'}>{source.selected ? '取消长期复用' : '加入长期素材'}</Button></div>
        </article>)}
      </div>
      <div className="flex items-center gap-3"><Button disabled={pages.length < 2} onClick={() => setPages(values => values.slice(0, -1))} variant="outline">上一页</Button><span>第 {pages.length} 页</span>
        <Button disabled={data.next_cursor === null} onClick={() => setPages(values => [...values, data.next_cursor!])} variant="outline">下一页</Button></div>
    </> : !error && <p>正在读取来源素材…</p>}
    {selected && <SourceDetail ctx={ctx} identity={selected} key={selected} onClose={() => setSelected(null)} />}
  </section>
}

export function SourceDetail({ ctx, identity, onClose }: { ctx: PluginContext; identity: string; onClose: () => void }) {
  const [source, setSource] = useState<Source | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let disposed = false
    void ctx.rest<Source>(`/sources/${encodeURIComponent(identity)}`).then(value => { if (!disposed) { setSource(value) } })
      .catch(reason => { if (!disposed) { setError(String(reason)) } })

    return () => { disposed = true }
  }, [ctx, identity])

  return <Dialog onOpenChange={open => { if (!open) { onClose() } }} open><DialogContent className="max-h-[85vh] space-y-4 overflow-auto sm:max-w-4xl">
    <DialogHeader><DialogTitle>{source?.title || '读取图文详情'}</DialogTitle><DialogDescription>原始来源、参考图片和内容引用记录</DialogDescription></DialogHeader>
    {error && <p role="alert">{error}</p>}
    {source && <>
      <div className="flex flex-wrap items-center gap-2"><span className="break-all text-xs text-muted-foreground">{source.url}</span><CopyButton label="复制来源链接" text={source.url}>复制来源链接</CopyButton></div>
      <p className="text-xs text-muted-foreground">作者：{source.author || '未提供'} · 发布时间：{source.published_at || '未提供'} · 采集时间：{source.collected_at ? formatTimestamp(source.collected_at) : '未记录'}</p>
      {source.truncated && <p className="text-sm text-muted-foreground">正文已截取，原提取结果约 {source.original_chars} 字符；分析仅依据当前保存的片段。</p>}
      {source.attempts && <p className="text-xs text-muted-foreground">该来源当日读取尝试：{source.attempts} 次</p>}
      {source.images?.length ? <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3">{source.images.map((image, index) => <figure className="space-y-2" key={`${image.url}:${index}`}>
        <ReferencePreview ctx={ctx} image={image} /><figcaption className="text-xs text-muted-foreground">{image.id ? '参考图片 · 尚未授权公开发布' : image.error || '仅保留原图链接'}<CopyButton label={`复制原图链接 ${index + 1}`} text={image.url}>复制原图链接</CopyButton></figcaption>
      </figure>)}</div> : <p className="text-xs text-muted-foreground">此来源没有采集到图片，已保留正文。</p>}
      {source.summary && <p className="rounded-lg bg-muted/30 p-3">{source.summary}</p>}
      <div className="max-h-[32rem] overflow-auto whitespace-pre-wrap break-words select-text">{source.text || source.error || '未取得正文'}</div>
      <CopyButton label="复制来源图文记录" text={() => JSON.stringify(source, null, 2)}>复制完整图文记录</CopyButton>
      <details><summary className="cursor-pointer">已引用此来源的内容版本（{source.content_versions?.length || 0}）</summary>{source.content_versions?.map(item => <p className="text-sm" key={item.id}>{item.title} · {item.day}</p>)}</details>
    </>}
  </DialogContent></Dialog>
}
