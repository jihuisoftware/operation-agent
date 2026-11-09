import { Button, host, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import { openWriter, writingPath } from './navigation'
import { base } from './types'
interface Summary {
  id: string
  title: string
  updated: string
  revision: number
  content_id?: string
}

interface Props { ctx: PluginContext }

export function WritingList({ ctx }: Props) {
  const [rows, setRows] = useState<Summary[]>([]),
    [error, setError] = useState(''),
    [before, setBefore] = useState(''),
    [next, setNext] = useState(''),
    [revision, setRevision] = useState(0),
    [busy, setBusy] = useState(false)

  useEffect(() => {
    let live = true
    void ctx
      .rest<{ items: Summary[]; next?: string }>(`${base}?before=${encodeURIComponent(before)}`)
      .then(value => {
        if (live) {
          setRows(value.items)
          setNext(value.next || '')
          setError('')
        }
      })
      .catch(reason => {
        if (live) {
          setError(String(reason))
        }
      })

    return () => {
      live = false
    }
  }, [ctx, before, revision])

  const action = async (row: Summary, copy: boolean) => {
    setBusy(true)

    try {
      const result = await ctx.rest<{ id: string }>(copy ? base : `${base}/${row.id}/archive`, {
        method: 'POST',
        body: {
          ...(copy ? { copy_from: row.id } : { expected_revision: row.revision }),
          request_id: crypto.randomUUID()
        }
      })

      if (copy) {
        host.navigate(writingPath(`draft=${result.id}`))
      } else {
        setRevision(n => n + 1)
      }
    } catch (reason) {
      setError(String(reason))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4 p-4">
      <div className="flex gap-2">
        <Button onClick={() => openWriter()}>手动写稿</Button>
        <Button onClick={() => setRevision(n => n + 1)} variant="outline">
          刷新草稿
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">写作草稿支持长文和自动保存，提交审核后才生成正式版本。</p>
      {error && <p role="alert">{error}</p>}
      {rows.map(row => (
        <article className="flex flex-wrap items-center gap-3 border-b py-4" key={row.id}>
          <div className="mr-auto">
            <h2>{row.title || '未命名草稿'}</h2>
            <p className="text-xs text-muted-foreground">
              {new Date(row.updated).toLocaleString('zh-CN')}
              {row.content_id ? ' · 已提交过审核' : ''}
            </p>
          </div>
          <Button onClick={() => host.navigate(writingPath(`draft=${row.id}`))}>继续编辑</Button>
          <Button disabled={busy} onClick={() => void action(row, true)} variant="outline">
            另存副本
          </Button>
          <Button disabled={busy} onClick={() => void action(row, false)} variant="ghost">
            归档
          </Button>
        </article>
      ))}
      {!rows.length && !error && <p>暂无写作草稿</p>}
      {next && <Button onClick={() => setBefore(next)}>更早草稿</Button>}
      {before && <Button onClick={() => setBefore('')}>返回最新</Button>}
    </div>
  )
}
