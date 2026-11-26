import { CopyButton, Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, formatTimestamp, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

import { type ReferenceImage, ReferencePreview } from './source-image-preview'

export interface Source {
  document_language?: string
  origins?: { type: string; query?: string; language?: string; feed?: string; keyword?: string; seen: string }[]
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

export function SourceDetail({
  ctx,
  identity,
  onClose
}: {
  ctx: PluginContext
  identity: string
  onClose: () => void
}) {
  const [source, setSource] = useState<Source | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let disposed = false
    void ctx
      .rest<Source>(`/sources/${encodeURIComponent(identity)}`)
      .then(value => {
        if (!disposed) {
          setSource(value)
        }
      })
      .catch(reason => {
        if (!disposed) {
          setError(String(reason))
        }
      })

    return () => {
      disposed = true
    }
  }, [ctx, identity])

  return (
    <Dialog
      onOpenChange={open => {
        if (!open) {
          onClose()
        }
      }}
      open
    >
      <DialogContent className="max-h-[85vh] space-y-4 overflow-auto sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>{source?.title || '读取图文详情'}</DialogTitle>
          <DialogDescription>原始来源、参考图片和内容引用记录</DialogDescription>
        </DialogHeader>
        {error && <p role="alert">{error}</p>}
        {source && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <span className="break-all text-xs text-muted-foreground">{source.url}</span>
              <CopyButton label="复制来源链接" text={source.url}>
                复制来源链接
              </CopyButton>
            </div>
            <p className="text-xs text-muted-foreground">
              作者：{source.author || '未提供'} · 发布时间：{source.published_at || '未提供'} · 采集时间：
              {source.collected_at ? formatTimestamp(source.collected_at) : '未记录'}
            </p>
            <div className="text-xs text-muted-foreground">
              <p>正文语言：{source.document_language === 'en' ? '英文' : source.document_language === 'zh' ? '中文' : source.document_language ? '未知' : '未记录'}</p>
              {source.origins?.length ? source.origins.map(o => <p key={JSON.stringify(o)}>
                {o.type === 'search' ? `${o.language === 'en' ? '英文检索' : '中文检索'} · ${o.keyword} → ${o.query}` : o.type === 'rss' ? `订阅：${o.feed}` : '指定网址'} · {o.seen}
              </p>) : <p>发现依据：未记录</p>}
            </div>
            {source.truncated && (
              <p className="text-sm text-muted-foreground">
                正文已截取，原提取结果约 {source.original_chars} 字符；分析仅依据当前保存的片段。
              </p>
            )}
            {source.attempts && (
              <p className="text-xs text-muted-foreground">该来源当日读取尝试：{source.attempts} 次</p>
            )}
            {source.images?.length ? (
              <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3">
                {source.images.map((image, index) => (
                  <figure className="space-y-2" key={`${image.url}:${index}`}>
                    <ReferencePreview ctx={ctx} image={image} />
                    <figcaption className="text-xs text-muted-foreground">
                      {image.id ? '参考图片 · 尚未授权公开发布' : image.error || '仅保留原图链接'}
                      <CopyButton label={`复制原图链接 ${index + 1}`} text={image.url}>
                        复制原图链接
                      </CopyButton>
                    </figcaption>
                  </figure>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">此来源没有采集到图片，已保留正文。</p>
            )}
            {source.summary && <p className="rounded-lg bg-muted/30 p-3">{source.summary}</p>}
            <div className="max-h-[32rem] overflow-auto whitespace-pre-wrap break-words select-text">
              {source.text || source.error || '未取得正文'}
            </div>
            <CopyButton label="复制来源图文记录" text={() => JSON.stringify(source, null, 2)}>
              复制完整图文记录
            </CopyButton>
            <details>
              <summary className="cursor-pointer">
                已引用此来源的内容版本（{source.content_versions?.length || 0}）
              </summary>
              {source.content_versions?.map(item => (
                <p className="text-sm" key={item.id}>
                  {item.title} · {item.day}
                </p>
              ))}
            </details>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
