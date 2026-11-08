import { Button, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import { AssetImage } from '../asset-image'
import { CoverStudio } from '../cover-studio'
import type { RecordRow } from '../types'

import type { Writer } from './controller'
import { projection } from './projection'
import { base, type Preview } from './types'

interface Props { controller: Writer; ctx: PluginContext }

export function WritingPanels({ controller, ctx }: Props) {
  const { draft, dirty } = useValue(controller.state)
  const current = projection(draft.document, draft.cover_asset_id)

  const [sources, setSources] = useState<RecordRow[]>([]),
    [preview, setPreview] = useState<Preview | null>(null),
    [error, setError] = useState(''),
    [coverOpen, setCoverOpen] = useState(false)

  useEffect(() => {
    let live = true
    void ctx
      .rest<{ sources: RecordRow[] }>('/content/editor-options')
      .then(value => {
        if (live) {
          setSources(value.sources)
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
  }, [ctx])

  const check = async () => {
    try {
      await controller.save()
      setPreview(await ctx.rest<Preview>(`${base}/${draft.id}/preview`))
      setError('')
    } catch (reason) {
      setError(String(reason))
    }
  }

  return (
    <aside className="w-full space-y-5 border-t p-4 xl:w-80 xl:shrink-0 xl:border-l xl:border-t-0">
      <details open>
        <summary>原创与来源</summary>
        <label className="my-3 block text-sm">
          <input
            checked={draft.original}
            disabled={draft.origin.kind !== 'original'}
            onChange={event => controller.edit({ original: event.target.checked })}
            type="checkbox"
          />{' '}
          我确认这是一篇本人原创手稿
        </label>
        {draft.origin.kind !== 'original' && <p className="text-xs">此稿派生自已有内容，保留原稿依据及权限约束。</p>}
        <div className="max-h-60 overflow-auto">
          {sources.map(source => (
            <label className="block text-sm" key={source.id}>
              <input
                checked={draft.source_ids.includes(source.id)}
                onChange={event =>
                  controller.edit({
                    source_ids: event.target.checked
                      ? [...draft.source_ids, source.id]
                      : draft.source_ids.filter(id => id !== source.id)
                  })
                }
                type="checkbox"
              />
              {String(source.title || source.id)}
            </label>
          ))}
        </div>
      </details>
      <details>
        <summary>正文图片与封面选择</summary>
        {current.asset_ids.map(id => (
          <div key={id}>
            <AssetImage ctx={ctx} id={id} />
            <Button
              aria-pressed={draft.cover_asset_id === id}
              onClick={() => controller.edit({ cover_asset_id: id })}
              size="sm"
              variant="outline"
            >
              设为封面
            </Button>
          </div>
        ))}
        {draft.cover_asset_id && (
          <Button onClick={() => controller.edit({ cover_asset_id: '' })} variant="ghost">
            取消独立封面
          </Button>
        )}
      </details>
      <details onToggle={event => setCoverOpen(event.currentTarget.open)}>
        <summary>封面设计</summary>
        {draft.cover_asset_id && <AssetImage ctx={ctx} id={draft.cover_asset_id} />}
        {coverOpen && (
          <CoverStudio
            ctx={ctx}
            refresh={async () => undefined}
            row={{ id: draft.id, title: draft.title, asset_ids: draft.cover_asset_id ? [draft.cover_asset_id] : [] }}
            working={{
              preview: async spec => {
                await controller.save()

                return ctx.rest(`${base}/${draft.id}/covers/preview`, {
                  method: 'POST',
                  body: { cover: spec, expected_revision: controller.state.get().draft.revision }
                })
              },
              apply: async id => {
                controller.edit({ cover_asset_id: id })
                await controller.save()
              }
            }}
          />
        )}
      </details>
      <details open>
        <summary>发布预览与图片顺序</summary>
        <p className="text-sm">
          标题 {Array.from(draft.title).length} 字 · 正文 {current.body_characters} 字 · {current.asset_ids.length} 张图
        </p>
        <p className="my-2 text-xs">
          发布为纯文本图文，格式会降级。当前通道标题最多 20 字、正文 900 字、图片 18 张。长稿可另存副本后自行精简。
        </p>
        <Button onClick={() => void check()} variant="outline">
          保存并检查发布预览
        </Button>
        {dirty && preview && <p className="text-xs">内容已修改，请更新预览。</p>}
        {preview && (
          <div className="space-y-2 py-3">
            <p className="whitespace-pre-wrap break-words">{preview.body}</p>
            <p>
              {Array.from(preview.body).length} 字 · {preview.asset_ids.length} 张图
            </p>
            {preview.asset_ids.map((id, index) => (
              <div key={id}>
                <p>第 {index + 1} 张</p>
                <AssetImage ctx={ctx} id={id} />
              </div>
            ))}
            {preview.automatic_cover && <p>提交审核时自动制作本地文字封面。</p>}
            {[...preview.issues, ...preview.warnings].map(text => (
              <p className="text-sm" key={text}>
                {text}
              </p>
            ))}
          </div>
        )}
      </details>
      {error && <p role="alert">{error}</p>}
    </aside>
  )
}
