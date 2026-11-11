import { Button, Codicon, type PluginContext } from '@hermes/plugin-sdk'
import { useState } from 'react'

import { AssetImage } from './asset-image'
import type { RecordRow } from './types'

export function Records({ rows }: { rows: RecordRow[] }) {
  return (
    <div className="grid gap-2">
      {rows.length ? (
        rows.map(row => (
          <details className="rounded border p-2" key={row.id}>
            <summary>
              {String(row.title || row.name || row.stage || row.kind || row.id)} · {String(row.state || row.day || '')}
            </summary>
            <pre className="overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(row, null, 2)}</pre>
          </details>
        ))
      ) : (
        <p>暂无记录；执行后会显示实际结果。</p>
      )}
    </div>
  )
}

export function NewRecord({
  ctx,
  kind,
  onSaved,
  onError
}: {
  ctx: PluginContext
  kind: string
  onSaved: () => Promise<unknown>
  onError: (error: string) => void
}) {
  const [text, setText] = useState('')

  return (
    <div className="mb-4 flex gap-2">
      <textarea
        className="flex-1 border bg-transparent p-2"
        onChange={e => setText(e.target.value)}
        placeholder={
          kind === 'task'
            ? '补充当日任务、优先级或截止要求'
            : '导入指标 JSON：包含 id、day、name、value、definition、source；缺失值填 null'
        }
        value={text}
      />
      <button
        onClick={() => {
          try {
            const body =
              kind === 'task' ? { text, created: new Date().toISOString(), state: 'pending' } : JSON.parse(text)

            void ctx
              .rest(`/records/${kind}`, { method: 'POST', body })
              .then(onSaved)
              .then(() => setText(''))
              .catch(error => onError(String(error)))
          } catch (error) {
            onError(String(error))
          }
        }}
      >
        添加{kind === 'task' ? '任务' : '指标'}
      </button>
    </div>
  )
}

export function Assets({
  ctx,
  rows,
  content,
  refresh,
  onError
}: {
  ctx: PluginContext
  rows: RecordRow[]
  content: RecordRow[]
  refresh: () => Promise<unknown>
  onError: (error: string) => void
}) {
  const [authorized, setAuthorized] = useState(false)
  const [removed, setRemoved] = useState<string[]>([])

  async function removeAsset(id: string) {
    setRemoved(current => [...current, id])

    try {
      await ctx.rest(`/assets/${encodeURIComponent(id)}/revoke`, { method: 'POST', body: {} })
    } catch (error) {
      setRemoved(current => current.filter(value => value !== id))
      onError(String(error))

      return
    }

    try {
      await refresh()
    } catch (error) {
      onError(String(error))
    }
  }

  return (
    <div className="grid gap-3">
      <label>
        <input checked={authorized} onChange={e => setAuthorized(e.target.checked)} type="checkbox" />{' '}
        我确认所选素材可用于当前账号公开发布
      </label>
      <input
        accept="image/png,image/jpeg,image/webp"
        aria-label="上传图片素材"
        disabled={!authorized}
        multiple
        onChange={async e => {
          const input = e.currentTarget
          const files = Array.from(input.files || [])
          input.value = ''

          try {
            for (const file of files) {
              if (file.size > 20 * 1024 * 1024) {
                throw new Error('图片不能超过 20 MB')
              }

              const data = await new Promise<string>((resolve, reject) => {
                const reader = new FileReader()
                reader.onload = () => resolve(String(reader.result).split(',')[1])
                reader.onerror = reject
                reader.readAsDataURL(file)
              })

              const uploaded = await ctx.rest<{ id: string }>('/assets', {
                method: 'POST',
                body: { name: file.name, data, authorized }
              })

              setRemoved(current => current.filter(id => id !== uploaded.id))
            }

            await refresh()
          } catch (error) {
            onError(String(error))
          }
        }}
        type="file"
      />
      <div className="grid grid-cols-[repeat(auto-fill,minmax(10rem,13rem))] gap-4">
        {rows
          .filter(row => !row.revoked && !removed.includes(row.id))
          .map(row => (
            <div className="min-w-0 space-y-2" key={row.id}>
              <div className="relative aspect-square overflow-hidden rounded-lg bg-(--ui-bg-quaternary)">
                <AssetImage className="h-full w-full object-cover" ctx={ctx} id={row.id} />
                <Button
                  aria-label={`删除图片：${String(row.name)}`}
                  className="absolute right-2 top-2"
                  onClick={() => void removeAsset(row.id)}
                  size="icon-xs"
                  title="删除图片"
                  type="button"
                  variant="floating"
                >
                  <Codicon name="close" />
                </Button>
              </div>
              <p className="truncate text-xs" title={String(row.name)}>{String(row.name)}</p>
            </div>
          ))}
      </div>
      <h2>内容版本</h2>
      <Records rows={content} />
    </div>
  )
}

export function download(day: string, markdown: string) {
  const url = URL.createObjectURL(new Blob([markdown], { type: 'text/markdown;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${day}-运营日报.md`
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
