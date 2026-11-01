import { host, type PluginContext } from '@hermes/plugin-sdk'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { WritableAtom } from 'nanostores'
import { afterEach, expect, it, vi } from 'vitest'

import { ActionEvidence, PublicationStatus } from './action-evidence'
import type { RecordRow } from './types'

vi.mock('@hermes/plugin-sdk', async importOriginal => {
  const sdk = await importOriginal<Record<string, unknown>>()
  const { atom } = await import('nanostores')

  return { ...sdk, host: { state: { requestOwner: atom({ connectionId: 'local', profile: 'one' }) } } }
})

const requestOwner = host.state.requestOwner as WritableAtom<{ connectionId: string; profile: string }>
const originalOwner = requestOwner.get()
afterEach(() => { cleanup(); requestOwner.set(originalOwner); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('copies all or only failed steps and loads screenshot evidence under the owning Profile', async () => {
  const owner = { connectionId: 'local', profile: 'evidence' }
  requestOwner.set(owner)
  const write = vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText: write } })

  const steps = [
    { event_id: 1, command_id: 'command', sequence: 1, name: 'baseline', phase: 'completed', at: '2026-11-01T02:00:00Z', result: { ids: ['old'] } },
    { event_id: 2, command_id: 'command', sequence: 2, name: 'verify_publication', phase: 'failed', at: '2026-11-01T02:01:00Z', error: '标题不一致', evidence_id: 'shot', duration_ms: 1600 }
  ]

  const rest = vi.fn(async (path: string) => path.includes('/steps') ? { steps } : { image: 'data:image/png;base64,aW1hZ2U=' })
  const row: RecordRow = { id: 'action', state: 'submitted' }
  render(<><PublicationStatus result={{ publication: { execution: 'verified', platform: 'reviewing', content: 'mismatch' } }} /><ActionEvidence ctx={{ rest } as unknown as PluginContext} row={row} /></>)
  expect(screen.getByText('平台：审核中')).toBeTruthy()
  fireEvent.click(screen.getByText('网页执行步骤与证据'))
  await screen.findByText(/核对发布内容 · 异常/)
  fireEvent.click(screen.getByRole('button', { name: '复制完整网页过程' }))
  await waitFor(() => expect(write).toHaveBeenCalledWith(JSON.stringify({ action: row, steps }, null, 2)))
  fireEvent.click(screen.getByRole('button', { name: '仅复制网页错误' }))
  await waitFor(() => expect(write).toHaveBeenCalledTimes(2))
  expect(JSON.parse(write.mock.calls[1][0]).errors).toEqual([steps[1]])
  fireEvent.click(screen.getByText(/核对发布内容 · 异常/))
  fireEvent.click(screen.getByRole('button', { name: '查看现场截图' }))
  expect(await screen.findByAltText('网页步骤现场截图')).toBeTruthy()
  expect(rest).toHaveBeenCalledWith('/browser-evidence/shot', { owner })
})

it('drops the expanded log and ignores a late response after switching Profile', async () => {
  requestOwner.set({ connectionId: 'local', profile: 'first' })
  let finish!: (result: unknown) => void
  const rest = vi.fn(() => new Promise(resolve => { finish = resolve }))
  render(<ActionEvidence ctx={{ rest } as unknown as PluginContext} row={{ id: 'action', state: 'submitted' }} />)
  fireEvent.click(screen.getByText('网页执行步骤与证据'))
  await waitFor(() => expect(rest).toHaveBeenCalledTimes(1))
  await act(async () => requestOwner.set({ connectionId: 'local', profile: 'second' }))
  await act(async () => finish({ steps: [{ event_id: 1, command_id: 'command', sequence: 1, name: '旧配置私有记录', phase: 'completed', at: '' }] }))
  expect(screen.queryByText(/旧配置私有记录/)).toBeNull()
  expect(screen.queryByRole('button', { name: '复制完整网页过程' })).toBeNull()
})
