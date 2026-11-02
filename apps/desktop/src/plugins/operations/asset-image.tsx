import type { PluginContext } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'

export function AssetImage({ ctx, id }: { ctx: PluginContext; id: string }) {
  const [image, setImage] = useState<{ name: string; data: string; mime?: string } | null>(null)
  useEffect(() => {
    let disposed = false
    void ctx
      .rest<{ name: string; data: string; mime?: string }>(`/assets/${encodeURIComponent(id)}?thumbnail=true`)
      .then(value => {
        if (!disposed) {
          setImage(value)
        }
      })
      .catch(() => {
        if (!disposed) {
          setImage(null)
        }
      })

    return () => {
      disposed = true
    }
  }, [ctx, id])

  return image ? (
    <img
      alt={image.name}
      className="max-h-56 w-full rounded object-contain"
      loading="lazy"
      src={`data:${image.mime || 'image/png'};base64,${image.data}`}
    />
  ) : (
    <p className="text-xs text-muted-foreground">图片待加载或已撤回</p>
  )
}
