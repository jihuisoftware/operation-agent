import { Button, CopyButton, LogView, type PluginContext } from '@hermes/plugin-sdk'
import { useState } from 'react'

import { number, statuses, useUsage } from './data'
import type { CallDetail } from './types'
import { purposeLabel } from './visuals'

interface Props { ctx: PluginContext; identity: string; query?: string }

export function CallDetailToggle({ ctx, identity, query = '' }: Props) {
  const [open, setOpen] = useState(false)

  return <div><Button aria-expanded={open} onClick={() => setOpen(value => !value)} variant="link">{open ? '收起请求详情' : '查看请求详情'}</Button>
    {open && <RequestDetail ctx={ctx} identity={identity} key={identity} query={query} />}
  </div>
}

export function RequestDetail({ ctx, identity, query = '' }: Props) {
  const [selected, setSelected] = useState(identity)
  const filters = new URLSearchParams(query)
  const scope = new URLSearchParams()

  for (const key of ['filter_business', 'filter_topic']) {
    if (filters.has(key)) { scope.set(key, filters.get(key)!) }
  }

  const { data, error, retry } = useUsage<CallDetail>(ctx, `/usage/calls/${encodeURIComponent(selected)}?${scope}`)

  if (!data) {
    return <div>{error ? <p role="alert">读取请求详情失败：{error}</p> : <p role="status">正在读取请求详情…</p>}<Button onClick={retry} variant="ghost">重新读取</Button></div>
  }

  const { call, detail, attempts } = data
  const duration = call.received == null ? '进行中' : `${Math.max(0, call.received - call.started).toFixed(1)} 秒`
  const cost = detail?.cost
  const costText = cost?.amount == null ? '未知（未获得费用回执）' : `${cost.amount} ${cost.currency || '币种未提供'} · 提供方回执`

  return <section aria-label="请求详情" className="space-y-3 py-3 text-sm">
    <header className="flex flex-wrap items-center gap-3"><h3 className="font-semibold">任务：{purposeLabel(call.stage) || call.task_name}</h3><CopyButton label="复制请求详情" text={JSON.stringify(data, null, 2)} /><Button onClick={retry} variant="ghost">刷新详情</Button></header>
    {error && <p role="alert">详情可能已过期：{error}</p>}
    <p>{call.model || '未知模型'} / {call.provider || '未知提供方'} · {detail ? statuses[detail.state] || detail.state : statuses[call.state] || call.state} · {duration}</p>
    <p>输入 Token：{number(call.prompt_tokens)} · 输出 Token：{number(call.output_tokens)} · 缓存读取：{number(call.cache_read_tokens)} · 缓存写入：{number(call.cache_write_tokens)}</p>
    <p className="text-xs text-muted-foreground">缓存 Token 已包含在输入中；推理 Token 已包含在输出中。</p>
    <p>费用及来源：{costText}</p>
    {data.notice && <p role="status">{data.notice}</p>}
    {detail?.error && <p role="alert">请求失败：{detail.error}</p>}
    {detail?.parse_error && <p role="alert">解析失败：{detail.parse_error}</p>}
    <TextBlock label="输入提示词与请求参数" value={detail?.request} />
    <TextBlock label="输出原文" value={detail?.raw_response} />
    <TextBlock label="解析结果" value={detail?.parsed_result} />
    <div className="space-y-2"><h4 className="font-medium">重试记录</h4>
      <p className="text-xs text-muted-foreground">{attempts.length > 1 ? `本次业务调用共尝试 ${attempts.length} 次，各次用量分别记录。` : '没有关联的其他尝试记录。'}</p>
      {attempts.map((attempt, index) => <Button aria-pressed={selected === attempt.id} key={attempt.id} onClick={() => setSelected(attempt.id)} variant="ghost">{index === 0 ? '首次请求' : `重试 ${index}`} · {attempt.model || '未知模型'} / {attempt.provider || '未知提供方'} · {statuses[attempt.state] || attempt.state} · {number(attempt.total_tokens)} Token</Button>)}
    </div>
  </section>
}

function TextBlock({ label, value }: { label: string; value: unknown }) {
  const text = value == null ? '未保存或尚未返回' : typeof value === 'string' ? value : JSON.stringify(value, null, 2)

  return <details><summary className="cursor-pointer">{label}</summary><CopyButton label={`复制${label}`} text={text} /><LogView className="max-h-96">{text}</LogView></details>
}
