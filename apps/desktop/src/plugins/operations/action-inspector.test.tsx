import { host, type PluginContext } from '@hermes/plugin-sdk'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { WritableAtom } from 'nanostores'
import { afterEach, expect, it, vi } from 'vitest'

import { ActionInspector } from './action-inspector'
import { EvidenceStorage } from './evidence-storage'

vi.mock('@hermes/plugin-sdk', async importOriginal => {
  const sdk = await importOriginal<Record<string, unknown>>()
  const { atom } = await import('nanostores')

  return { ...sdk, host: { state: { requestOwner: atom({ connectionId: 'local', profile: 'work' }) }, navigate: vi.fn() } }
})
const owner = host.state.requestOwner as WritableAtom<{ connectionId: string; profile: string }>
afterEach(() => { cleanup(); owner.set({ connectionId: 'local', profile: 'work' }); vi.restoreAllMocks() })

const detail = {
  issue: { kind: 'mismatch', title: '内容不一致', help: '先核对差异，不重复发布' },
  tracking: { state: 'active', attempts: 1, next_check_at: '2026-11-01T12:00:00Z' },
  snapshot: { account_id: 'me', policy_version: 2, content: { title: '批准标题', body: '批准正文' }, assets: [{ id: 'cover', name: '封面.png' }], sources: [] },
  manual_history: [{ id: 'human', actor: '本机操作员', at: '2026-11-01T10:00:00Z', state: 'published', evidence: '人工核对证据', previous_result: { url: 'https://example.org/note' } }]
}

it('previews the frozen manuscript lazily and only requests read-only verification', async () => {
  let queued = false

  const rest = vi.fn(async (path: string) => {
    if (path.endsWith('/check')) { queued = true;

 return { command_id: 'review' } }

    if (path.includes('/images/')) { return { name: 'cover.png', data: 'aW1hZ2U=' } }

    return { ...detail, tracking: { ...detail.tracking, state: queued ? 'queued' : 'active' } }
  })

  render(<ActionInspector ctx={{ rest } as unknown as PluginContext} refresh={async () => {}} row={{ id: 'action', kind: 'publish', state: 'submitted', result: JSON.stringify({ actual: { title: '实际标题', body: '实际正文' } }) }} />)
  await screen.findByText('内容不一致')
  expect(rest.mock.calls.some(([path]) => path.includes('/images/'))).toBe(false)
  fireEvent.click(screen.getByText('最终稿与内容对比'))
  await screen.findByText('批准标题')
  expect(screen.getByText('实际标题')).toBeTruthy()
  await screen.findByAltText('内容核对图片')
  fireEvent.click(screen.getByRole('button', { name: '立即核对（不重发）' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/actions/action/check', { method: 'POST', owner: { connectionId: 'local', profile: 'work' } }))
  await screen.findByText(/只读核对已排队/)
  expect((screen.getByRole('button', { name: '立即核对（不重发）' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByText('人工核对历史（1）'))
  expect(screen.getByText('人工核对证据')).toBeTruthy()
})

it('discards a late detail response after changing Profile', async () => {
  let finish!: (value: unknown) => void
  const rest = vi.fn().mockImplementationOnce(() => new Promise(resolve => { finish = resolve })).mockResolvedValue({ ...detail, issue: { ...detail.issue, title: '新配置' } })
  render(<ActionInspector ctx={{ rest } as unknown as PluginContext} refresh={async () => {}} row={{ id: 'same-id', state: 'submitted' }} />)
  await waitFor(() => expect(rest).toHaveBeenCalledTimes(1))
  act(() => owner.set({ connectionId: 'local', profile: 'other' }))
  await screen.findByText('新配置')
  await act(async () => finish(detail))
  expect(screen.queryByText('内容不一致')).toBeNull()
})

it('saves retention selection before cleanup and reports protected evidence', async () => {
  let settings = { days: 30, automatic: false }
  const stats = () => ({ settings, database_bytes: 20000, reusable_bytes: 1000, categories: [{ kind: 'browser_evidence', count: 2, bytes: 500 }] })

  const rest = vi.fn(async (path: string, options?: { method?: string; body?: typeof settings }) => {
    if (options?.method === 'PUT') { settings = options.body!;

 return settings }

    return path.endsWith('/cleanup') ? { ...stats(), steps_deleted: 2, screenshots_deleted: 1 } : stats()
  })

  render(<EvidenceStorage ctx={{ rest } as unknown as PluginContext} />)
  fireEvent.click(screen.getByText('日志与截图存储管理'))
  await screen.findByText(/数据库占用/)
  fireEvent.change(screen.getByLabelText('证据保留期限'), { target: { value: '7' } })
  expect((screen.getByRole('button', { name: '清理到期记录' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '保存保留设置' }))
  await screen.findByText('保留设置已保存')
  fireEvent.click(screen.getByRole('button', { name: '清理到期记录' }))
  await screen.findByText(/已清理 2 条过期步骤和 1 张截图/)
  expect(settings).toEqual({ days: 7, automatic: false })
})
