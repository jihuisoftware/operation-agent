import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { SourceLibrary } from './source-library'

afterEach(cleanup)

it('jumps directly to the last, first and entered page and resets search to page one', async () => {
  const rest = vi.fn(async (path: string) => {
    const params = new URL(path, 'http://localhost').searchParams

    return { version: 1, topic: '测试', total: 73, selected_count: 0, items: [],
      page: Number(params.get('page') || 1), total_pages: 4 }
  })

  render(<SourceLibrary ctx={{ rest } as unknown as PluginContext} />)
  expect(await screen.findByText('第 1 页 / 共 4 页')).toBeTruthy()
  expect((screen.getByRole('button', { name: '首页' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '末页' }))
  expect(await screen.findByText('第 4 页 / 共 4 页')).toBeTruthy()
  expect(rest).toHaveBeenCalledWith('/sources?q=&page=4')
  expect((screen.getByRole('button', { name: '下一页' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '首页' }))
  await screen.findByText('第 1 页 / 共 4 页')
  fireEvent.change(screen.getByRole('spinbutton', { name: '跳转页码' }), { target: { value: '5' } })
  expect((screen.getByRole('button', { name: '跳转' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.change(screen.getByRole('spinbutton', { name: '跳转页码' }), { target: { value: '3' } })
  fireEvent.submit(screen.getByRole('button', { name: '跳转' }).closest('form')!)
  expect(await screen.findByText('第 3 页 / 共 4 页')).toBeTruthy()
  expect(rest).toHaveBeenCalledWith('/sources?q=&page=3')
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: '收纳' } })
  fireEvent.click(screen.getByRole('button', { name: '搜索' }))
  await screen.findByText('第 1 页 / 共 4 页')
  expect(rest).toHaveBeenCalledWith('/sources?q=%E6%94%B6%E7%BA%B3&page=1')
})

it('shows saved picture/text material and pins historical evidence without publishing', async () => {
  const source = { id: 's1', title: '厨房整理资料', url: 'https://example.org/a', state: 'read', excerpt: '收纳摘要', text: '完整原始正文', images: [{ id: 'image', url: 'https://example.org/image', state: 'saved' }], selected: false }

  const rest = vi.fn(async (path: string, options?: any) => {
    if (path === '/sources/s1/reuse') { source.selected = options.body.enabled;

 return {} }

    if (path === '/sources/s1') { return { ...source, content_versions: [{ id: 'c', title: '内容版本一', day: '2026-11-01' }] } }

    if (path === '/sources/images/image') { return { mime: 'image/png', data: 'abc' } }

    return { version: 9, topic: '收纳', total: 1, selected_count: Number(source.selected), items: [{ ...source }], page: 1, total_pages: 1 }
  })

  render(<SourceLibrary ctx={{ rest } as unknown as PluginContext} />)
  expect(await screen.findByText('厨房整理资料')).toBeTruthy()
  expect(await screen.findByAltText('采集来源的参考图片')).toBeTruthy()
  expect(screen.getByAltText('采集来源的参考图片').getAttribute('src')).toBe('data:image/png;base64,abc')
  fireEvent.click(screen.getByRole('button', { name: '加入长期素材' }))
  expect(await screen.findByRole('button', { name: '取消长期复用' })).toBeTruthy()
  expect(rest).toHaveBeenCalledWith('/sources/s1/reuse', { method: 'POST', body: { version: 9, enabled: true } })
  fireEvent.click(screen.getByRole('button', { name: '查看图文' }))
  expect(await screen.findByText('完整原始正文')).toBeTruthy()
  expect(screen.getByText('参考图片 · 尚未授权公开发布')).toBeTruthy()
  expect(screen.getByText('内容版本一 · 2026-11-01')).toBeTruthy()
  expect(rest.mock.calls.every(([path]) => path.startsWith('/sources'))).toBe(true)
})

it('searches and pages through historical sources while showing retrieval failures', async () => {
  const rest = vi.fn(async (path: string) => ({ version: 1, topic: '测试', total: 25, selected_count: 0,
    items: [{ id: 'bad', title: '失败来源', url: 'https://example.org', state: 'unavailable', error: '正文读取失败' }], page: Number(new URL(path, 'http://localhost').searchParams.get('page') || 1), total_pages: 2 }))

  render(<SourceLibrary ctx={{ rest } as unknown as PluginContext} />)
  expect(await screen.findByText('正文读取失败')).toBeTruthy()
  expect((screen.getByRole('button', { name: '加入长期素材' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '下一页' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/sources?q=&page=2'))
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: '收纳' } })
  fireEvent.click(screen.getByRole('button', { name: '搜索' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/sources?q=%E6%94%B6%E7%BA%B3&page=1'))
})
