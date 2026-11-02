import { Badge, Button, Codicon, Input, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

interface Topic {
  title: string
  reason: string
  source_ids: string[]
  origin?: string
}
interface TopicCatalog {
  version: number
  day: string
  scope_topic: string
  brief_id: string | null
  candidates: Topic[]
  selected: Topic | null
}

export function TopicsPanel({ ctx }: { ctx: PluginContext }) {
  const [data, setData] = useState<TopicCatalog | null>(null)
  const [title, setTitle] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [pending, setPending] = useState(false)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let disposed = false
    let busy = false

    const refresh = async () => {
      if (busy) { return }
      busy = true

      try {
        const next = await ctx.rest<TopicCatalog>('/topics')

        if (!disposed) { setData(next); setError('') }
      } catch (error) {
        if (!disposed) { setError(String(error)) }
      } finally { busy = false }
    }

    void refresh()
    const timer = setInterval(() => { if (!document.hidden) { void refresh() } }, 5000)

    return () => { disposed = true; clearInterval(timer) }
  }, [ctx, revision])

  const choose = async (choice: { title: string } | { candidate_index: number; brief_id: string | null }) => {
    if (!data) { return }
    setPending(true)
    setError('')

    try {
      const selected = await ctx.rest<Topic>('/topics/select', { method: 'POST', body: { ...choice, version: data.version } })
      setData({ ...data, selected })
      setRevision(value => value + 1)
      setNotice('已保存。下一次内容生产使用此题目；已有草稿不会被改写。')
    } catch (error) { setError(String(error)) }
    finally { setPending(false) }
  }

  return <section aria-label="选题管理" className="max-w-4xl space-y-5">
    <header className="flex items-center justify-between"><h2 className="flex items-center gap-2 text-lg font-semibold"><Codicon name="lightbulb" />选题管理</h2>
      <Button onClick={() => setRevision(value => value + 1)} variant="ghost">刷新选题</Button></header>
    {error && <p className="text-destructive" role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {!data && !error && <p>正在读取选题…</p>}
    {data && <>
      <p className="text-xs text-muted-foreground">{data.day} · 运营主题：{data.scope_topic || '未设置'}</p>
      <div className="space-y-3 rounded-lg bg-muted/30 p-4">
        <label className="grid gap-2">手动指定选题<Input maxLength={200} onChange={e => setTitle(e.target.value)} placeholder="例如：小户型厨房如何用 300 元改善收纳" value={title} /></label>
        <Button disabled={pending || !title.trim()} onClick={() => void choose({ title })}>使用这个选题</Button>
        <p className="text-xs text-muted-foreground">指定题目不会立即生产或发布；生成内容仍需可追溯来源。</p>
      </div>
      <div className="flex flex-wrap items-center gap-2"><Badge>当前选题</Badge><strong>{data.selected?.title || (data.candidates[0]?.title || '尚未确定')}</strong>
        <span className="text-xs text-muted-foreground">{data.selected ? '用户已指定' : data.candidates.length ? '默认使用首个推荐' : '可手动输入，或单独执行选题策划'}</span></div>
      <h3 className="font-medium">自动推荐</h3>
      {!data.candidates.length && <p className="text-muted-foreground">暂无候选。采集并整理归类后，需执行独立的“选题策划”模块。</p>}
      {data.candidates.map((topic, index) => <article className="space-y-2 border-b pb-4" key={`${data.brief_id}:${index}`}>
        <div className="flex items-center justify-between gap-3"><h4 className="font-medium">{index + 1}. {topic.title}</h4>
          <Button disabled={pending} onClick={() => void choose({ candidate_index: index, brief_id: data.brief_id })} variant="outline">选用</Button></div>
        <p className="text-sm text-muted-foreground">{topic.reason || '依据本批来源整理'}</p>
        <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">来源依据 · {topic.source_ids.length} 条</summary>
          <p className="break-all select-text">{topic.source_ids.join('、')}</p></details>
      </article>)}
    </>}
  </section>
}
