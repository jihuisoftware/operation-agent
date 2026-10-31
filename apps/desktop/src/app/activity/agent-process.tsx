import { useStore } from '@nanostores/react'

import type { ResolvedOwner } from '@/api/client'
import { CopyButton } from '@/components/ui/copy-button'
import type { ChatMessage } from '@/lib/chat-messages'
import { $sessions } from '@/store/session'
import { $sessionStates, knownOwnerForSession } from '@/store/session-states'

export function AgentProcess({ owner }: { owner: ResolvedOwner }) {
  const states = useStore($sessionStates)
  const sessions = useStore($sessions)

  const active = Object.entries(states).filter(([id, state]) => {
    const route = knownOwnerForSession(id)

    if (!state.busy || !route) {return false}

    if (typeof route === 'string') {return !owner.connectionId && route === (owner.profile || 'default')}

    return route.connectionId === owner.connectionId && (route.profile || 'default') === (owner.profile || 'default')
  })

  return (
    <section aria-label="Agent 执行过程" className="space-y-4">
      <h2 className="font-medium">Agent 执行过程</h2>
      {!active.length && <p className="text-muted-foreground">当前连接未收到正在执行的 Agent 会话。定时脚本的执行过程见下方。</p>}
      {active.map(([id, state]) => {
        const lastUser = state.messages.findLastIndex(message => message.role === 'user')
        const messages = state.messages.slice(Math.max(lastUser, 0)).filter(message => !message.hidden)

        return (
          <details className="space-y-3" key={id} open>
            <summary className="cursor-pointer font-medium">{sessions.find(s => s.id === state.storedSessionId)?.title || state.storedSessionId || id} · {state.needsInput ? '等待用户输入' : state.turnLive ? '正在执行' : '等待执行确认'}</summary>
            <p className="text-xs text-muted-foreground">{state.provider} · {state.model} · {state.turnStartedAt ? new Date(state.turnStartedAt).toLocaleString() : '开始时间待确认'}</p>
            <ProcessMessages messages={messages} />
          </details>
        )
      })}
    </section>
  )
}

export function ProcessMessages({ messages }: { messages: ChatMessage[] }) {
  return <div className="space-y-3 text-xs">{messages.map(message => (
    <div className="space-y-2" key={message.id}>
      {message.parts.map((part, index) => {
        if (part.type === 'text') {return <pre className="select-text whitespace-pre-wrap break-words font-sans" key={index}>{part.text}</pre>}

        if (part.type !== 'tool-call') {return null}
        const text = JSON.stringify({ arguments: part.args, result: part.result }, null, 2)

        return <details key={part.toolCallId} open={part.result === undefined && !part.interrupted || undefined}>
          <summary className="cursor-pointer font-medium">{part.toolName} · {part.interrupted ? '已中断' : part.result === undefined ? '执行中／等待结果' : '已返回结果'}</summary>
          <p>{part.timestamp ? new Date(part.timestamp * 1000).toLocaleString() : ''}</p>
          <CopyButton showLabel text={text} />
          <pre className="max-h-80 select-text overflow-auto whitespace-pre-wrap break-words">{text}</pre>
        </details>
      })}
      {message.error && <p className="text-destructive">{message.error}</p>}
    </div>
  ))}</div>
}
