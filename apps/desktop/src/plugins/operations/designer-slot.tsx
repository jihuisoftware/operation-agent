import { Button, host, CoverDesignerPanels, type CoverDesignerProps, type PluginContext } from '@hermes/plugin-sdk'

import { AssetImage } from './asset-image'
import type { RecordRow } from './types'
import type { Writer } from './writing/controller'

interface SlotProps {
  ctx: PluginContext
  row: RecordRow
  refresh: () => Promise<unknown>
  writer?: Writer
}

async function upload(file: File, authorized?: boolean) {
  if (!authorized || file.size > 20 * 1024 * 1024) {
    throw new Error('请确认图片使用授权，并选择不超过 20 MB 的图片')
  }

  const data = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1])
    reader.onerror = () => reject(new Error('无法读取图片'))
    reader.readAsDataURL(file)
  })

  return { data, name: file.name, authorized }
}

export function DesignerSlot({ ctx, row, writer, refresh }: SlotProps) {
  const kind = writer ? 'writing' : 'content'
  const origin = { kind, origin_id: row.id }

  const props: CoverDesignerProps = {
    title: String(row.title ?? ''),
    detail: id => ctx.rest('/cover-designer/' + encodeURIComponent(id)),
    latest: () => ctx.rest('/cover-designer?' + new URLSearchParams(origin)),
    image: id => <AssetImage ctx={ctx} id={id} />,
    start: async ({ file, authorized, ...request }) => {
      await writer?.save()
      const state = writer?.state.get()

      if (state?.dirty || state?.conflict) { throw new Error('请先保存草稿后再生成封面') }

      return ctx.rest('/cover-designer', { method: 'POST', body: {
        ...origin, ...request, revision: state?.draft.revision ?? row.content_revision,
        version: state?.draft.policy_version ?? row.policy_version, ...(file ? { upload: await upload(file, authorized) } : {})
      } })
    },
    apply: async (id, candidateAsset) => {
      await writer?.save()

      const result = await ctx.rest<{ asset_id: string; revision: number; job_id?: string }>(
        '/cover-designer/' + encodeURIComponent(id) + '/apply', { method: 'POST', body: { ...origin, candidate_asset: candidateAsset } })

      if (writer) {
        const state = writer.state.get()

        if (state.dirty || state.conflict || state.draft.revision !== result.revision) {
          throw new Error('草稿已变化，请重新预览')
        }

        await writer.applyDesignerCover(result.asset_id, result.job_id ?? id)
      } else {
        await refresh()
      }
    }
  }

  return <CoverDesignerPanels key={kind + ':' + row.id} panel={props} fallback={<Button onClick={() => host.navigate('/settings?tab=plugins')} variant="outline">安装或启用封面设计插件</Button>} />
}
