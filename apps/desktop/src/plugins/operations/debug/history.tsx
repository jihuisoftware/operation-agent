import { Button, Codicon, formatTimestamp } from '@hermes/plugin-sdk'

import { DebugRecord, type Detail, type Run, states } from './records'

interface Props {
  runs: Run[]
  selected: string | null
  detail: Detail | null
  clearing: boolean
  cancelling: boolean
  cancelAvailable: boolean
  clearAvailable: boolean
  notice: string
  onClear: () => void
  onCancel: () => void
  onSelect: (id: string | null) => void
}

export function DebugHistory({ runs, selected, detail, clearing, cancelling, clearAvailable, cancelAvailable, notice, onClear, onCancel, onSelect }: Props) {
  return <section className="space-y-3">
    <div className="flex items-center justify-between gap-3">
      <h2 className="font-semibold">调试记录</h2>
      <div className="flex gap-2"><Button disabled={cancelling || clearing || !cancelAvailable} onClick={onCancel} variant="outline">
        {cancelling ? '正在取消…' : '取消所有批次'}
      </Button><Button disabled={clearing || cancelling || !clearAvailable || !runs.length} onClick={onClear}
        title={!clearAvailable ? '后台更新后可使用历史清除功能' : undefined} variant="outline">
        {clearing ? '正在清除…' : '一键清除历史记录'}
      </Button></div>
    </div>
    <p className="text-xs text-muted-foreground">仅清除当前主题已结束的调试历史；保留运行中、暂停待继续任务及业务数据。</p>
    <p className="text-xs text-muted-foreground">取消所有批次会停止当前主题未结束的调试任务；已发出的模型请求可能需等待返回，已提交动作保留核对记录。</p>
    {notice && <p role="status">{notice}</p>}
    {!runs.length && <p>尚无调试记录。</p>}
    {runs.map(item => <article className="rounded border" key={item.id}>
      <Button aria-controls={`debug-record-${item.id}`} aria-expanded={selected === item.id}
        className="w-full justify-start text-left" onClick={() => onSelect(selected === item.id ? null : item.id)} variant="ghost">
        <Codicon name={selected === item.id ? 'chevron-down' : 'chevron-right'} />
        {item.title} · {states[item.state] || item.state} · <time dateTime={item.started} title={item.started}>{formatTimestamp(item.started)}</time>
      </Button>
      {selected === item.id && <div className="p-3" id={`debug-record-${item.id}`}>
        {detail?.run.id === item.id ? <DebugRecord detail={detail} key={item.id} /> : <p>正在读取记录…</p>}
      </div>}
    </article>)}
  </section>
}
