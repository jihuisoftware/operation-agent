import { Button, GlyphSpinner, host, useValue } from '@hermes/plugin-sdk'

import { sameLoginOwner } from './login-state'
import { $operationsBrowserActivity, $showOperationsBrowser } from './state'
import type { BrowserCommand } from './types'

const taskLabels: Record<BrowserCommand['kind'], string> = {
  account: '核对登录账号', inbox: '读取互动消息', publish: '发布内容', interact: '执行互动', verify: '核对操作结果'
}

export function LiveViewButton() {
  const owner = useValue(host.state.requestOwner)
  const activity = useValue($operationsBrowserActivity)
  const visible = useValue($showOperationsBrowser)
  const running = activity && sameLoginOwner(owner, activity.owner) ? activity : null
  const message = running ? `正在操作网页：${taskLabels[running.kind]}` : '显示或隐藏自动运营内嵌网页'

  return <Button aria-label="运营画面" aria-pressed={visible} onClick={() => $showOperationsBrowser.set(!visible)} size="sm" title={message} variant="ghost">
    运营画面
    {running && <GlyphSpinner ariaLabel={message} className="size-3" />}
  </Button>
}
