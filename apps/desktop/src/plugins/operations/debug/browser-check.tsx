import { Button } from '@hermes/plugin-sdk'
import { useState } from 'react'

interface Props {
  busy: boolean
  onCheck: () => Promise<{ state: string; detail: string }>
}

export function BrowserCheck({ busy, onCheck }: Props) {
  const [checking, setChecking] = useState(false)
  const [detail, setDetail] = useState('')

  const check = async () => {
    setChecking(true)
    setDetail('正在只读检查账号和搜索页；慢网络加载最多等待 2 分钟，可人工接管中断')

    try { setDetail((await onCheck()).detail) } catch (reason) { setDetail(String(reason)) } finally { setChecking(false) }
  }

  return <div className="space-y-2">
    <Button disabled={busy || checking} onClick={() => void check()} variant="outline">只读检查账号与搜索页</Button>
    {detail && <p className="text-sm" role="status">{detail}</p>}
  </div>
}
