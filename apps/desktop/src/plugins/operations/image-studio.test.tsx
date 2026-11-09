import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { ImageStudio } from './image-studio'
afterEach(cleanup)

const job = {
  id: 'visual-set:one',
  state: 'completed',
  detail: '组图完成',
  attempts: [{ state: 'completed' }],
  pages: [{ asset_id: 'image', title: '主题封面', has_art: true }],
  review: { pass: true, reason: '清晰' }
}

it('does not generate on open; explicit generation saves latest draft and explicit apply replaces images', async () => {
  const rest = vi.fn(async (path: string) =>
    path.startsWith('/visual-sets?') ? { item: null } : path === '/visual-sets' ? job : { data: 'aW1hZ2U=' }
  )

  const prepare = vi.fn(async () => ({ expected_revision: 7 })),
    apply = vi.fn(async () => {})

  render(
    <ImageStudio
      apply={apply}
      ctx={{ rest } as unknown as PluginContext}
      identity="draft"
      kind="writing"
      prepare={prepare}
    />
  )
  await waitFor(() => expect(rest).toHaveBeenCalledOnce())
  expect(prepare).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: '生成整套图文' }))
  await screen.findByText('1. 主题封面')
  expect(rest).toHaveBeenCalledWith('/visual-sets', {
    method: 'POST',
    body: expect.objectContaining({
      kind: 'writing',
      id: 'draft',
      expected_revision: 7,
      request_id: expect.any(String)
    })
  })
  expect(apply).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: '应用整套组图（替换当前配图）' }))
  await waitFor(() => expect(apply).toHaveBeenCalledWith(job.id))
  expect(rest.mock.calls.some(([path]) => path.includes('publish') || path.includes('approve'))).toBe(false)
})
it('uses an explicit paid retry for one art page without requesting a whole new manuscript', async () => {
  const rest = vi.fn(async (path: string) =>
    path.startsWith('/visual-sets?') ? { item: job } : path === '/visual-sets' ? job : { data: 'aW1hZ2U=' }
  )

  render(
    <ImageStudio
      apply={async () => {}}
      ctx={{ rest } as unknown as PluginContext}
      identity="content"
      kind="content"
      prepare={async () => ({ content_revision: 'fp' })}
    />
  )
  fireEvent.click(await screen.findByRole('button', { name: '重做此页主视觉（1 次生图）' }))
  await waitFor(() =>
    expect(rest).toHaveBeenCalledWith('/visual-sets', {
      method: 'POST',
      body: expect.objectContaining({ retry: true, regenerate_art: 0, content_revision: 'fp' })
    })
  )
})
