import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { CoverStudio } from './cover-studio'

afterEach(cleanup)

it('labels same-style candidates separately and clears their variant when switching style', async () => {
  const socialOptions = { ...options, templates: [{ id: 'xiaohongshu', label: '小红书版' }],
    social_styles: [{ id: 'soft', label: '柔和' }, { id: 'handwriting', label: '手写' }] }

  const socialCandidates = ['上下引言', '侧边引言', '细框留白'].map((label, index) => ({
    asset_id: `soft-${index}`, template_label: '小红书版 · 柔和', palette_label: '深海蓝', variant_label: label,
    cover: { ...spec, template: 'xiaohongshu', style: 'soft', variant: ['quotation', 'margin', 'frame'][index] }
  }))

  const rest = vi.fn(async (path: string) => {
    if (path === '/content/cover-options') {return socialOptions}

    if (path.includes('/covers/preview')) {return { ...socialOptions, candidates: socialCandidates, set_id: 'set' }}

    return { data: 'aW1hZ2U=' }
  })

  render(<CoverStudio ctx={{ rest } as unknown as PluginContext} refresh={async () => {}}
    row={{ ...row, cover: socialCandidates[0].cover, cover_candidates: socialCandidates }} />)
  await screen.findByLabelText('小红书封面风格')
  fireEvent.click(screen.getByRole('button', { name: '选用细框留白' }))
  fireEvent.change(screen.getByLabelText('小红书封面风格'), { target: { value: 'handwriting' } })
  fireEvent.click(screen.getByRole('button', { name: '生成三个候选封面' }))
  await screen.findByText('三个候选已就绪。本地排版，不调用模型；请同时检查大图和小图。')
  const call = rest.mock.calls.find(([path]) => path.includes('/covers/preview'))
  expect(call).toBeTruthy()
  expect(rest).toHaveBeenCalledWith('/content/draft/covers/preview', expect.objectContaining({
    body: expect.objectContaining({ cover: expect.objectContaining({ style: 'handwriting', variant: undefined, palette: 'blue' }) })
  }))
})

it('passes the chosen social-note style to the existing preview endpoint', async () => {
  const rest = vi.fn(async (path: string) => {
    if (path === '/content/cover-options') {return { ...options,
      templates: [...options.templates, { id: 'xiaohongshu', label: '小红书版' }],
      social_styles: [{ id: 'basic', label: '基础' }, { id: 'handwriting', label: '手写' }] }}

    if (path.includes('/covers/preview')) {return { ...options, candidates, set_id: 'social-set' }}

    return { data: 'aW1hZ2U=' }
  })

  render(<CoverStudio ctx={{ rest } as unknown as PluginContext} refresh={async () => {}} row={row} />)
  await screen.findByLabelText('封面版式')
  fireEvent.change(screen.getByLabelText('封面版式'), { target: { value: 'xiaohongshu' } })
  fireEvent.change(screen.getByLabelText('小红书封面风格'), { target: { value: 'handwriting' } })
  fireEvent.click(screen.getByRole('button', { name: '生成三个候选封面' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/content/draft/covers/preview', expect.objectContaining({
    method: 'POST', body: expect.objectContaining({ cover: expect.objectContaining({ template: 'xiaohongshu', style: 'handwriting' }) })
  })))
  await screen.findByText('三个候选已就绪。本地排版，不调用模型；请同时检查大图和小图。')
})
const spec = { title: '独立封面标题', subtitle: '来源与方法', eyebrow: '工具观察', keywords: ['核对'], template: 'editorial', palette: 'blue', size: 'normal' }
const candidates = ['编辑精选', '醒目标题', '清单要点'].map((label, index) => ({ asset_id: 'candidate-' + index, cover: { ...spec, template: ['editorial', 'spotlight', 'checklist'][index] }, template_label: label, palette_label: '深海蓝' }))
const options = { templates: [{ id: 'editorial', label: '编辑精选' }, { id: 'spotlight', label: '醒目标题' }, { id: 'checklist', label: '清单要点' }], palettes: [{ id: 'blue', label: '深海蓝', color: '#123456' }] }
const row = { id: 'draft', title: '文章原始标题', content_revision: 'fingerprint', policy_version: 4, asset_ids: ['original', 'second'] }

it('previews three local variants and updates the original content with the selected cover', async () => {
  const rest = vi.fn(async (path: string) => {
    if (path === '/content/cover-options') { return options }

    if (path.includes('/covers/preview')) { return { ...options, candidates, set_id: 'set' } }

    if (path.includes('/assets/')) { return { data: 'aW1hZ2U=', mime: 'image/png' } }

    return { id: 'draft', updated_in_place: true, original_schedule_retained: false }
  })

  const refresh = vi.fn(async () => {})
  render(<CoverStudio ctx={{ rest } as unknown as PluginContext} refresh={refresh} row={row} />)
  await screen.findByLabelText('封面版式')
  fireEvent.change(screen.getByLabelText('封面主标题'), { target: { value: spec.title } })
  fireEvent.click(screen.getByRole('button', { name: '生成三个候选封面' }))
  await screen.findByRole('button', { name: '选用醒目标题' })
  fireEvent.click(screen.getByRole('button', { name: '选用醒目标题' }))
  fireEvent.click(screen.getByRole('button', { name: '应用封面并保存' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/content/draft/versions', { method: 'POST', body: {
    asset_ids: ['candidate-1', 'second'], cover_set_id: 'set', version: 4, content_revision: 'fingerprint',
    request_id: expect.any(String)
  } }))
  expect(await screen.findByText('封面已更新到原内容，原审核与排期已失效；请重新审核后安排发布。')).toBeTruthy()
  expect(rest.mock.calls.some(([path]) => path.includes('/approve') || path.includes('/generate'))).toBe(false)
  expect(refresh).toHaveBeenCalledOnce()
})

it('uses cached candidates and refuses applying an image after its text has changed', async () => {
  const rest = vi.fn(async (path: string) => path === '/content/cover-options' ? options : { data: 'aW1hZ2U=' })
  render(<CoverStudio ctx={{ rest } as unknown as PluginContext} refresh={async () => {}} row={{ ...row, cover: spec, cover_candidates: candidates }} />)
  await screen.findByLabelText('封面版式')
  fireEvent.click(screen.getByRole('button', { name: '选用醒目标题' }))
  expect((screen.getByRole('button', { name: '应用封面并保存' }) as HTMLButtonElement).disabled).toBe(false)
  fireEvent.change(screen.getByLabelText('封面副标题'), { target: { value: '新副标题' } })
  expect((screen.getByRole('button', { name: '应用封面并保存' }) as HTMLButtonElement).disabled).toBe(true)
  expect(screen.getByText('文字或样式已修改，请重新生成候选后再应用。')).toBeTruthy()
  expect(rest.mock.calls.some(([path]) => path.includes('/covers/preview'))).toBe(false)
})

it('drops a withdrawn saved candidate and keeps other covers selectable', async () => {
  const rest = vi.fn(async (path: string) => {
    if (path === '/content/cover-options') { return options }

    if (path.startsWith('/assets/candidate-0')) { throw new Error('404: {"detail":"素材不存在或已撤回"}') }

    return { data: 'aW1hZ2U=' }
  })

  render(<CoverStudio ctx={{ rest } as unknown as PluginContext} refresh={async () => {}}
    row={{ ...row, asset_ids: ['candidate-0'], cover_candidates: candidates }} />)
  await screen.findByText(/部分候选封面已失效/)
  expect(screen.queryByRole('button', { name: '选用编辑精选' })).toBeNull()
  expect(screen.queryByRole('button', { name: '查看大图' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '选用醒目标题' }))
  expect((screen.getByRole('button', { name: '应用封面并保存' }) as HTMLButtonElement).disabled).toBe(false)
})

it('selects a specific pose within its group and drops the old placeholder on preview', async () => {
  const choices = { ...options, templates: [{ id: 'cartoon', label: '卡通波点' }], cartoon_characters: [
    { id: 'kico', label: '软萌小白', group: 'Kico' },
    { id: 'rabbit', label: '托盘女仆', group: '粉红兔子' },
    { id: 'rabbit-foot', label: '抱臂伸脚', group: '粉红兔子' }
  ] }
  const rest = vi.fn(async (path: string) => path.endsWith('cover-options') ? choices :
    { ...choices, candidates, set_id: 'set' })
  render(<CoverStudio ctx={{ rest } as unknown as PluginContext} refresh={async () => {}}
    row={{ ...row, cover: { ...spec, template: 'cartoon', variant: 'kico', eyebrow: '主题分享' } }} />)
  fireEvent.change(await screen.findByLabelText('角色类型'), { target: { value: '粉红兔子' } })
  fireEvent.change(screen.getByLabelText('角色造型'), { target: { value: 'rabbit-foot' } })
  fireEvent.click(screen.getByRole('button', { name: '生成三个候选封面' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/content/draft/covers/preview', expect.objectContaining({
    body: expect.objectContaining({ cover: expect.objectContaining({ variant: 'rabbit-foot', eyebrow: '' }) })
  })))
})

it('rotates five poses three at a time independently of the selected cover', async () => {
  const poses = ['1', '2', '3', '4', '5'].map(id => ({ id, label: id, group: '兔子' }))
  const options = { templates: [{ id: 'cartoon', label: '卡通波点' }], palettes: [],
    cartoon_characters: [...poses, { id: 'other', label: '小猫', group: '猫' }] }
  const working = {
    apply: vi.fn(),
    preview: vi.fn(async (cover: typeof spec & { variant?: string }) => {
      const start = poses.findIndex(pose => pose.id === cover.variant)
      const candidates = [0, 1, 2].map(offset => {
        const { id } = poses[(start + offset) % poses.length]
        return { asset_id: id, variant_label: id, template_label: '卡通波点', palette_label: '粉色', cover: { ...cover, variant: id } }
      })
      return { ...options, candidates, set_id: '' }
    })
  }
  const rest = vi.fn(async (path: string) => path.endsWith('cover-options') ? options : { data: 'aW1hZ2U=' })
  render(<CoverStudio ctx={{ rest } as unknown as PluginContext} working={working} refresh={async () => {}}
    row={{ ...row, cover: { ...spec, template: 'cartoon', variant: '1' } }} />)
  await screen.findByLabelText('角色造型')
  const shown = () => screen.getAllByRole('button', { name: /^选用/ }).map(button => button.textContent)
  fireEvent.click(screen.getByRole('button', { name: '生成三个候选封面' }))
  await screen.findByRole('button', { name: '选用1' })
  expect(shown()).toEqual(['选用1', '选用2', '选用3'])
  fireEvent.click(screen.getByRole('button', { name: '选用2' }))
  fireEvent.click(screen.getByRole('button', { name: '换一换' }))
  await screen.findByRole('button', { name: '选用4' })
  expect(shown()).toEqual(['选用4', '选用5', '选用1'])
  fireEvent.click(screen.getByRole('button', { name: '换一换' }))
  await screen.findByRole('button', { name: '选用2' })
  expect(shown()).toEqual(['选用2', '选用3', '选用4'])
})
