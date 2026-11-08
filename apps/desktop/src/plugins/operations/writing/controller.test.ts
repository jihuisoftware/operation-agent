import type { PluginContext } from '@hermes/plugin-sdk'
import { afterEach, expect, it, vi } from 'vitest'

import { writer } from './controller'
import type { Draft } from './types'
const copies = vi.hoisted(() => new Map())
vi.mock('./journal', () => ({
  journal: vi.fn(async (key: string, value: unknown) => {
    if (value) {
      copies.set(key, structuredClone(value))
    }

    return copies.get(key)
  })
}))

const draft: Draft = {
  id: 'd',
  title: '',
  document: { type: 'doc', content: [{ type: 'paragraph' }] },
  document_version: 1,
  source_ids: [],
  original: false,
  cover_asset_id: '',
  revision: 1,
  updated: '',
  archived: false,
  origin: { kind: 'original' },
  policy_version: 1
}

afterEach(() => {
  vi.useRealTimers()
  copies.clear()
})
it('serializes saves, retains typing during a request, and does not replace editor content on acknowledgment', async () => {
  let release!: (value: object) => void

  const rest = vi
    .fn()
    .mockImplementationOnce(
      () =>
        new Promise(resolve => {
          release = resolve
        })
    )
    .mockResolvedValue({ revision: 3, updated: 'now' })

  const controller = writer({ rest } as unknown as PluginContext, 'scope', { draft, dirty: false })
  controller.edit({ title: '第一笔' })
  const saving = controller.save()
  await vi.waitFor(() => expect(rest).toHaveBeenCalledOnce())
  const document = { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: '输入中' }] }] }
  controller.edit({ title: '第二笔', document })
  release({ revision: 2, updated: 'then' })
  await saving
  expect(rest).toHaveBeenCalledTimes(2)
  expect(rest.mock.calls[1][1].body).toMatchObject({ title: '第二笔', expected_revision: 2 })
  expect(controller.state.get().draft.document).toBe(document)
  expect(controller.state.get().dirty).toBe(false)
  controller.dispose()
})
it('retries the exact uncertain request after offline recovery, then rejects stale-window overwrites', async () => {
  const rest = vi
    .fn()
    .mockRejectedValueOnce(new Error('network offline'))
    .mockResolvedValueOnce({ revision: 2 })
    .mockRejectedValueOnce(new Error('409 conflict'))

  const first = writer({ rest } as unknown as PluginContext, 'a', { draft, dirty: false })
  first.edit({ title: '离线稿' })
  await expect(first.save()).rejects.toThrow('offline')
  first.dispose()
  const recovered = writer({ rest } as unknown as PluginContext, 'a', copies.get('a'))
  await recovered.save()
  expect(rest.mock.calls[0][1].body).toEqual(rest.mock.calls[1][1].body)
  recovered.edit({ title: '本机修改' })
  await expect(recovered.save()).rejects.toThrow('409')
  expect(recovered.state.get()).toMatchObject({ conflict: true, dirty: true, draft: { title: '本机修改' } })
  expect(copies.has('other-profile')).toBe(false)
  recovered.dispose()
})
it('debounces two seconds and defers autosave during Chinese composition', async () => {
  vi.useFakeTimers()
  const rest = vi.fn().mockResolvedValue({ revision: 2 })
  const controller = writer({ rest } as unknown as PluginContext, 'scope', { draft, dirty: false })
  controller.composition(true)
  controller.edit({ title: '中' })
  await vi.advanceTimersByTimeAsync(3000)
  expect(rest).not.toHaveBeenCalled()
  controller.edit({ title: '中文输入' })
  controller.composition(false)
  await vi.advanceTimersByTimeAsync(1999)
  expect(rest).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(1)
  expect(rest).toHaveBeenCalledOnce()
  controller.dispose()
})

it('allows fixing a rejected document instead of endlessly retrying the invalid mutation', async () => {
  const rest = vi.fn().mockRejectedValueOnce(new Error('400 文档格式无效')).mockResolvedValueOnce({ revision: 2 })
  const controller = writer({ rest } as unknown as PluginContext, 'scope', { draft, dirty: false })
  controller.edit({ title: '非法格式' })
  await expect(controller.save()).rejects.toThrow('400')
  controller.edit({ title: '已修复格式' })
  await controller.save()
  expect(rest.mock.calls[1][1].body.title).toBe('已修复格式')
  expect(rest.mock.calls[1][1].body.request_id).not.toBe(rest.mock.calls[0][1].body.request_id)
  controller.dispose()
})
