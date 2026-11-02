import { Badge, Button, Codicon, CopyButton, formatTimestamp, Input, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import { ReferencePreview } from './source-library'

interface Material {
  id: string
  source_id: string
  title: string
  url: string
  category: string
  summary: string
  relevant: boolean
  facts: string[]
  opinions: string[]
  uncertainties: string[]
  keywords: string[]
  created: string
  source_day: string
  text_truncated: boolean
  images?: { id?: string; url: string; state: string }[]
}
interface Catalog {
  topic: string
  total: number
  organized: number
  usable: number
  pending: number
  matching: number
  categories: Record<string, number>
  items: Material[]
  next_cursor: number | null
}

export function OrganizedLibrary({
  ctx,
  initialQuery = '',
  initialCategory = ''
}: {
  ctx: PluginContext
  initialQuery?: string
  initialCategory?: string
}) {
  const [data, setData] = useState<Catalog | null>(null)
  const [search, setSearch] = useState(initialQuery)
  const [query, setQuery] = useState(initialQuery)
  const [category, setCategory] = useState(initialCategory)
  const [pages, setPages] = useState([0])
  const [revision, setRevision] = useState(0)
  const [error, setError] = useState('')
  const cursor = pages[pages.length - 1]
  useEffect(() => {
    let disposed = false
    let busy = false

    const refresh = async () => {
      if (busy) {
        return
      }

      busy = true

      try {
        const next = await ctx.rest<Catalog>(
          `/organized-sources?q=${encodeURIComponent(query)}&category=${encodeURIComponent(category)}&cursor=${cursor}`
        )

        if (!disposed) {
          setData(next)
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
  }, [ctx, query, category, cursor, revision])

  return (
    <section aria-label="资料整理与归类" className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Codicon name="library" />
          资料整理与归类
        </h2>
        <Button onClick={() => setRevision(value => value + 1)} variant="ghost">
          刷新资料
        </Button>
      </header>
      <p className="text-sm text-muted-foreground">
        采集 → 整理归类 → 选题 →
        内容生产。当日及已加入长期素材的相关资料用于后续生产；历史资料可在信息采集页选择复用。事实陈述来自原文，不代表已经独立核实。
      </p>
      {error && (
        <p className="text-destructive" role="alert">
          {error}
        </p>
      )}
      {!data && !error && <p>正在读取整理资料…</p>}
      {data && (
        <>
          <p className="text-sm text-muted-foreground">当前主题：{data.topic || '未设置'}</p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ['可用来源', data.total],
              ['已整理', data.organized],
              ['相关资料', data.usable],
              ['待整理', data.pending]
            ].map(([label, count]) => (
              <div className="rounded-lg bg-muted/30 p-3" key={label}>
                <div className="text-xs text-muted-foreground">{label}</div>
                <strong className="text-xl">{count}</strong>
              </div>
            ))}
          </div>
          <form
            className="flex flex-wrap gap-2"
            onSubmit={event => {
              event.preventDefault()
              setQuery(search.trim())
              setPages([0])
            }}
          >
            <Input
              aria-label="搜索整理资料"
              maxLength={200}
              onChange={e => setSearch(e.target.value)}
              placeholder="搜索摘要、关键词或原文标题"
              type="search"
              value={search}
            />
            <Button type="submit" variant="outline">
              搜索
            </Button>
          </form>
          <div aria-label="资料分类" className="flex flex-wrap gap-2">
            <Button
              aria-pressed={!category}
              onClick={() => {
                setCategory('')
                setPages([0])
              }}
              variant="ghost"
            >
              全部分类
            </Button>
            {Object.entries(data.categories).map(([name, count]) => (
              <Button
                aria-pressed={category === name}
                key={name}
                onClick={() => {
                  setCategory(name)
                  setPages([0])
                }}
                variant="ghost"
              >
                {name} · {count}
              </Button>
            ))}
          </div>
          {!!data.pending && (
            <p className="text-sm text-muted-foreground">
              还有 {data.pending} 条待整理。可在定时任务中启用“资料整理与归类”，开发时也可单独调试；已完成的资料会复用。
            </p>
          )}
          {!data.items.length && <p>暂无符合筛选条件的整理资料。</p>}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {data.items.map(row => (
              <MaterialCard ctx={ctx} key={row.id} row={row} />
            ))}
          </div>
          <div className="flex items-center gap-3">
            <Button
              disabled={pages.length === 1}
              onClick={() => setPages(value => value.slice(0, -1))}
              variant="outline"
            >
              上一页
            </Button>
            <span className="text-xs text-muted-foreground">
              共 {data.matching} 条 · 第 {pages.length} 页
            </span>
            <Button
              disabled={data.next_cursor === null}
              onClick={() => {
                if (data.next_cursor !== null) {
                  setPages(value => [...value, data.next_cursor!])
                }
              }}
              variant="outline"
            >
              下一页
            </Button>
          </div>
        </>
      )}
    </section>
  )
}

function MaterialCard({ ctx, row }: { ctx: PluginContext; row: Material }) {
  const groups: [string, string[]][] = [
    ['事实陈述（未独立核实）', row.facts],
    ['作者观点', row.opinions],
    ['待核实与限制', row.uncertainties]
  ]

  return (
    <article className="space-y-3 rounded-lg bg-muted/20 p-4">
      <ReferencePreview ctx={ctx} image={row.images?.find(image => image.id)} />
      <div className="flex flex-wrap gap-2">
        <Badge>{row.category}</Badge>
        <Badge>{row.relevant ? '供后续分析' : '不相关 · 不用于生产'}</Badge>
      </div>
      <h3 className="font-medium">{row.title || '未命名来源'}</h3>
      <p className="text-sm">{row.summary}</p>
      <div className="flex flex-wrap gap-2">
        {row.keywords.map(word => (
          <span className="text-xs text-muted-foreground" key={word}>
            #{word}
          </span>
        ))}
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer">查看整理详情与来源</summary>
        <div className="mt-3 space-y-3 select-text">
          {groups.map(([name, values]) => (
            <div key={name}>
              <h4 className="font-medium">{name}</h4>
              {values.length ? (
                <ul className="list-disc pl-5">
                  {values.map((value, index) => (
                    <li key={index}>{value}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground">未提取到内容</p>
              )}
            </div>
          ))}
          {row.text_truncated && <p>正文较长，本次整理覆盖前 6,000 字；其余内容仍在原始资料中。</p>}
          <p className="break-all">原始链接：{row.url}</p>
          <p className="text-xs text-muted-foreground">
            来源日期 {row.source_day} · 整理于 {formatTimestamp(row.created)}
          </p>
          <CopyButton label="复制完整整理记录" text={() => JSON.stringify(row, null, 2)}>
            复制完整整理记录
          </CopyButton>
        </div>
      </details>
    </article>
  )
}
