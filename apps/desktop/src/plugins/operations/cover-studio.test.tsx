import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { CoverStudio } from './cover-studio'

afterEach(cleanup)
const spec = { title: '独立封面标题', subtitle: '来源与方法', eyebrow: '工具观察', keywords: ['核对'], template: 'editorial', palette: 'blue', size: 'normal' }
const candidates = ['编辑精选', '醒目标题', '清单要点'].map((label, index) => ({ asset_id: 'candidate-' + index, cover: { ...spec, template: ['editorial', 'spotlight', 'checklist'][index] }, template_label: label, palette_label: '深海蓝' }))
const options = { templates: [{ id: 'editorial', label: '编辑精选' }, { id: 'spotlight', label: '醒目标题' }, { id: 'checklist', label: '清单要点' }], palettes: [{ id: 'blue', label: '深海蓝', color: '#123456' }] }
const row = { id: 'draft', title: '文章原始标题', content_revision: 'fingerprint', policy_version: 4, asset_ids: ['original', 'second'] }

it('previews three local variants and saves the selected cover as a new version', async () => {
  const rest = vi.fn(async (path: string) => {
    if (path === '/content/cover-options') { return options }

    if (path.includes('/covers/preview')) { return { ...options, candidates, set_id: 'set' } }

    if (path.includes('/assets/')) { return { data: 'aW1hZ2U=', mime: 'image/png' } }

    return { id: 'new-version', original_schedule_retained: true }
  })

  const refresh = vi.fn(async () => {})
  render(<CoverStudio ctx={{ rest } as unknown as PluginContext} refresh={refresh} row={row} />)
  await screen.findByLabelText('封面版式')
  fireEvent.change(screen.getByLabelText('封面主标题'), { target: { value: spec.title } })
  fireEvent.click(screen.getByRole('button', { name: '生成三个候选封面' }))
  await screen.findByRole('button', { name: '选用醒目标题' })
  fireEvent.click(screen.getByRole('button', { name: '选用醒目标题' }))
  fireEvent.click(screen.getByRole('button', { name: '应用封面并保存新版本' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/content/draft/versions', { method: 'POST', body: {
    asset_ids: ['candidate-1', 'second'], cover_set_id: 'set', version: 4, content_revision: 'fingerprint',
    request_id: expect.any(String), cancel_original_schedule: false
  } }))
  expect(await screen.findByText('已保存为新待审版本；旧版本排期仍然有效。')).toBeTruthy()
  expect(rest.mock.calls.some(([path]) => path.includes('/approve') || path.includes('/generate'))).toBe(false)
  expect(refresh).toHaveBeenCalledOnce()
})

it('uses cached candidates and refuses applying an image after its text has changed', async () => {
  const rest = vi.fn(async (path: string) => path === '/content/cover-options' ? options : { data: 'aW1hZ2U=' })
  render(<CoverStudio ctx={{ rest } as unknown as PluginContext} refresh={async () => {}} row={{ ...row, cover: spec, cover_candidates: candidates }} />)
  await screen.findByLabelText('封面版式')
  fireEvent.click(screen.getByRole('button', { name: '选用醒目标题' }))
  expect((screen.getByRole('button', { name: '应用封面并保存新版本' }) as HTMLButtonElement).disabled).toBe(false)
  fireEvent.change(screen.getByLabelText('封面副标题'), { target: { value: '新副标题' } })
  expect((screen.getByRole('button', { name: '应用封面并保存新版本' }) as HTMLButtonElement).disabled).toBe(true)
  expect(screen.getByText('文字或样式已修改，请重新生成候选后再应用。')).toBeTruthy()
  expect(rest.mock.calls.some(([path]) => path.includes('/covers/preview'))).toBe(false)
})
