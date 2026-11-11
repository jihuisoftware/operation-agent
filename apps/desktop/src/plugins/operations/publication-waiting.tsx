import { formatTimestamp } from '@hermes/plugin-sdk'

export interface PublicationWait {
  code: string
  detail: string
  last_seen: string | null
}

export function PublicationWaiting({ waiting }: { waiting?: PublicationWait }) {
  if (!waiting) { return null }

  return <div className="space-y-1 text-sm" role="status">
    <p>{waiting.detail}</p>
    {waiting.code === 'WORKER_OFFLINE' && <>
      <p className="text-xs text-muted-foreground">{waiting.last_seen ? `执行器最后连接：${formatTimestamp(waiting.last_seen)}` : '尚未收到桌面网页执行器连接。'}</p>
      <p>请保持桌面应用运行，并打开运营画面检查连接状态。恢复连接后，后台会重新检查发布条件。</p>
    </>}
  </div>
}
