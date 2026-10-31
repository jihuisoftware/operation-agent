import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import type { ClientSessionState } from '@/app/types'
import type { ChatMessage } from '@/lib/chat-messages'
import { $sessionStates } from '@/store/session-states'

import { AgentProcess, ProcessMessages } from './agent-process'

vi.mock('@/store/session-states', async importOriginal => ({
  ...(await importOriginal<Record<string, unknown>>()),
  knownOwnerForSession: (id: string) => ({ connectionId: id === 'ours' ? 'remote' : 'foreign', profile: 'work' })
}))

afterEach(() => { cleanup(); $sessionStates.set({}) })

it('shows public progress and tool arguments/results as they arrive', () => {
  const message: ChatMessage = { id: 'm1', role: 'assistant', parts: [
    { type: 'text', text: '正在读取来源' },
    { type: 'tool-call', toolCallId: 'call1', toolName: 'web_extract', args: { url: 'https://example.com' }, argsText: '{}' }
  ] }

  const view = render(<ProcessMessages messages={[message]} />)
  expect(screen.getByText('正在读取来源')).toBeTruthy()
  expect(screen.getByText(/web_extract · 执行中/)).toBeTruthy()
  view.rerender(<ProcessMessages messages={[{ ...message, parts: [{ ...message.parts[1], result: { text: '已取得正文' } } as ChatMessage['parts'][number]] }]} />)
  expect(screen.getByText('web_extract · 已返回结果')).toBeTruthy()
  expect(screen.getByText(/已取得正文/)).toBeTruthy()
})

it('never shows another connection’s active conversation', () => {
  const state = (text: string) => ({ busy: true, turnLive: true, messages: [{ id: text, role: 'user', parts: [{ type: 'text', text }] }] }) as ClientSessionState
  $sessionStates.set({ ours: state('本连接任务'), foreign: state('其他连接私有任务') })
  render(<AgentProcess owner={{ connectionId: 'remote', profile: 'work' }} />)
  expect(screen.getByText('本连接任务')).toBeTruthy()
  expect(screen.queryByText('其他连接私有任务')).toBeNull()
})
