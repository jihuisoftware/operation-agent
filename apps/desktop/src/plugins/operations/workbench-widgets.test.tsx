import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { Assets } from './workbench-widgets'

afterEach(cleanup)

it('hides withdrawn assets and removes an image through its own delete button', async () => {
  const rest = vi.fn(async () => ({ name: '可用.png', data: 'image' }))
  const refresh = vi.fn(async () => undefined)
  render(
    <Assets
      content={[]}
      ctx={{ rest } as unknown as PluginContext}
      onError={vi.fn()}
      refresh={refresh}
      rows={[
        { id: 'active', name: '可用.png' },
        { id: 'revoked', name: '已撤回.png', revoked: true }
      ]}
    />
  )
  expect(screen.queryByText(/已撤回.png/)).toBeNull()
  expect(rest).not.toHaveBeenCalledWith('/assets/revoked?thumbnail=true')
  fireEvent.click(screen.getByRole('button', { name: '删除图片：可用.png' }))
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce())
  expect(rest).toHaveBeenCalledWith('/assets/active/revoke', { method: 'POST', body: {} })
  expect(screen.queryByRole('button', { name: '删除图片：可用.png' })).toBeNull()
})

it('allows an explicitly authorized re-upload to show a deleted image again', async () => {
  const rest = vi.fn(async (path: string) =>
    path === '/assets' ? { id: 'active' } : { name: '可用.png', data: 'image' }
  )

  const refresh = vi.fn(async () => undefined)
  const onError = vi.fn()
  render(
    <Assets
      content={[]}
      ctx={{ rest } as unknown as PluginContext}
      onError={onError}
      refresh={refresh}
      rows={[{ id: 'active', name: '可用.png' }]}
    />
  )
  fireEvent.click(screen.getByRole('button', { name: '删除图片：可用.png' }))
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce())
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.change(screen.getByLabelText('上传图片素材'), {
    target: { files: [new File(['image'], '可用.png', { type: 'image/png' })] }
  })
  await waitFor(() => expect(refresh).toHaveBeenCalledTimes(2))
  expect(rest).toHaveBeenCalledWith('/assets', {
    method: 'POST',
    body: { name: '可用.png', data: 'aW1hZ2U=', authorized: true }
  })
  expect(screen.getByRole('button', { name: '删除图片：可用.png' })).toBeTruthy()
  expect(onError).not.toHaveBeenCalled()
})

it('restores a failed deletion and reports the error', async () => {
  const rest = vi.fn(async (path: string) => {
    if (path.endsWith('/revoke')) {
      throw new Error('连接中断')
    }

    return { name: '可用.png', data: 'image' }
  })

  const onError = vi.fn()
  render(
    <Assets
      content={[]}
      ctx={{ rest } as unknown as PluginContext}
      onError={onError}
      refresh={vi.fn()}
      rows={[{ id: 'active', name: '可用.png' }]}
    />
  )
  fireEvent.click(screen.getByRole('button', { name: '删除图片：可用.png' }))
  await waitFor(() => expect(onError).toHaveBeenCalledWith(expect.stringContaining('连接中断')))
  expect(screen.getByRole('button', { name: '删除图片：可用.png' })).toBeTruthy()
})
