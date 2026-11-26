import { Codicon, type PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

export interface ReferenceImage {
  id?: string
  url: string
  state: string
  error?: string
}

export function ReferencePreview({ ctx, image }: { ctx: PluginContext; image?: ReferenceImage }) {
  const [url, setUrl] = useState('')
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let disposed = false
    setUrl('')
    setFailed(false)

    if (image?.id) {
      void ctx
        .rest<{ mime: string; data: string }>(`/sources/images/${encodeURIComponent(image.id)}`)
        .then(data => {
          if (!disposed) {
            setUrl(`data:${data.mime};base64,${data.data}`)
          }
        })
        .catch(() => {
          if (!disposed) {
            setFailed(true)
          }
        })
    }

    return () => {
      disposed = true
    }
  }, [ctx, image?.id])

  return (
    <div className="flex aspect-video items-center justify-center overflow-hidden rounded-lg bg-muted/40">
      {url && !failed ? (
        <img
          alt="采集来源的参考图片"
          className="h-full w-full object-contain"
          loading="lazy"
          onError={() => setFailed(true)}
          src={url}
        />
      ) : (
        <span className="flex items-center gap-2 text-xs text-muted-foreground">
          <Codicon name="file-text" />
          {failed || image?.state === 'unavailable'
            ? '图片不可用 · 正文仍可查看'
            : image?.id
              ? '正在读取图片'
              : '文字资料'}
        </span>
      )}
    </div>
  )
}
