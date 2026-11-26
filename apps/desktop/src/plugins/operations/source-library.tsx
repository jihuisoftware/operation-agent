import { Badge, Button, Codicon, Input, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import { CollectionSummary, type CollectionSummaryData } from './collection-summary'
import { type Source, SourceDetail } from './source-detail'
import { ReferencePreview } from './source-image-preview'
import { SourcePagination } from './source-pagination'
import { WorkspaceReferences } from './workspace-references'

interface Catalog {
  latest_collection?: CollectionSummaryData | null
  version: number
  topic: string
  total: number
  selected_count: number
  items: Source[]
  page: number
  total_pages: number
}

export function SourceLibrary({
  ctx,
  initialQuery = '',
  initialSelected = null
}: {
  ctx: PluginContext
  initialQuery?: string
  initialSelected?: string | null
}) {
  const [data, setData] = useState<Catalog | null>(null)
  const [search, setSearch] = useState(initialQuery)
  const [query, setQuery] = useState(initialQuery)
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [selected, setSelected] = useState<string | null>(initialSelected)
  useEffect(() => {
    let disposed = false
    let busy = false

    const refresh = async () => {
      if (busy) {
        return
      }

      busy = true

      try {
        const result = await ctx.rest<Catalog>(`/sources?q=${encodeURIComponent(query)}&page=${page}`)

        if (!disposed) {
          setPage(result.page)
          setData(result)
          setError('')
        }
      } catch (reason) {
        if (!disposed) {
          setError(String(reason))
        }
      } finally {
        busy = false
      }
    }

    setData(null)
    void refresh()

    const timer = setInterval(() => {
      if (!document.hidden) {
        void refresh()
      }
    }, 5000)

    return () => {
      disposed = true
      clearInterval(timer)
    }
  }, [ctx, query, page, revision])

  const reuse = async (source: Source) => {
    if (!data) {
      return
    }

    setPending(true)

    try {
      await ctx.rest(`/sources/${encodeURIComponent(source.id)}/reuse`, {
        method: 'POST',
        body: { version: data.version, enabled: !source.selected }
      })
      setRevision(value => value + 1)
    } catch (reason) {
      setError(String(reason))
    } finally {
      setPending(false)
    }
  }

  return (
    <section aria-label="来源素材库" className="space-y-5">
      <WorkspaceReferences ctx={ctx} />
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Codicon name="library" />
          来源素材库
        </h2>
        <Button onClick={() => setRevision(value => value + 1)} variant="ghost">
          刷新素材
        </Button>
      </header>
      <p className="text-sm text-muted-foreground">
        采集资料自动保存图文。当天同主题资料经整理归类后用于选题；历史资料可设为当前主题的长期素材，跨天复用。参考图片不等于已获发布授权。
      </p>
      <form
        className="flex gap-2"
        onSubmit={event => {
          event.preventDefault()
          setQuery(search.trim())
          setPage(1)
        }}
      >
        <Input
          aria-label="搜索来源素材"
          maxLength={200}
          onChange={event => setSearch(event.target.value)}
          placeholder="按标题、正文或来源搜索"
          type="search"
          value={search}
        />
        <Button type="submit" variant="outline">
          搜索
        </Button>
      </form>
      {error && (
        <p className="text-destructive" role="alert">
          {error}
        </p>
      )}
      {data ? (
        <>
          {data.latest_collection && <CollectionSummary ctx={ctx} data={data.latest_collection} />}
          <p className="text-xs text-muted-foreground">
            {data.topic || '尚未设置主题'} · 共 {data.total} 条资料 · 长期复用 {data.selected_count} 条
          </p>
          {!data.items.length && <p>暂无匹配的来源；信息采集完成后会自动显示。</p>}
          <div className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-4">
            {data.items.map(source => (
              <article className="min-w-0 space-y-3 rounded-xl bg-muted/20 p-4" key={source.id}>
                <ReferencePreview ctx={ctx} image={source.images?.find(image => image.id)} />
                <div className="flex flex-wrap gap-2">
                  <Badge variant={source.state === 'read' ? 'success' : 'muted'}>
                    {source.state === 'read' ? '已采集' : '未取得正文'}
                  </Badge>
                  {source.selected && <Badge>已选复用</Badge>}
                </div>
                <h3 className="line-clamp-2 font-medium">{source.title}</h3>
                <p className="line-clamp-3 text-sm text-muted-foreground">
                  {source.summary || source.excerpt || source.error || '暂无正文'}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {source.author || '作者未提供'} · {source.scope_topic || '历史资料'}
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button onClick={() => setSelected(source.id)} variant="outline">
                    查看图文
                  </Button>
                  <Button
                    disabled={pending || !data.topic || source.state !== 'read'}
                    onClick={() => void reuse(source)}
                    variant={source.selected ? 'secondary' : 'ghost'}
                  >
                    {source.selected ? '取消长期复用' : '加入长期素材'}
                  </Button>
                </div>
              </article>
            ))}
          </div>
          <SourcePagination
            key={`${query}:${data.page}:${data.total_pages}`}
            onPageChange={setPage}
            page={data.page}
            totalPages={data.total_pages}
          />
        </>
      ) : (
        !error && <p>正在读取来源素材…</p>
      )}
      {selected && <SourceDetail ctx={ctx} identity={selected} key={selected} onClose={() => setSelected(null)} />}
    </section>
  )
}
