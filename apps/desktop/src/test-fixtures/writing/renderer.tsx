import './fixture.css'

import type { PluginContext } from '@hermes/plugin-sdk'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router'

import sample1 from '../../../../../docs/assets/visual-samples/page-1.webp?inline'
import sample2 from '../../../../../docs/assets/visual-samples/page-2.webp?inline'
import sample3 from '../../../../../docs/assets/visual-samples/page-3.webp?inline'
import { $workspaces, ownerKey } from '../../plugins/operations/workspace-state'
import { WritingPage } from '../../plugins/operations/writing/page'
import { projection } from '../../plugins/operations/writing/projection'
import type { Draft } from '../../plugins/operations/writing/types'

import { host } from './host'
import { recoveryProbe } from './recovery-probe'
const owner = host.state.requestOwner.get()
$workspaces.set({ [ownerKey(owner)]: { selected: { business_id: 'business', topic_id: 'topic' } } })

const initial: Draft = {
  id: 'fixture',
  title: '我的 Agent 开发笔记',
  document: { type: 'doc', content: [{ type: 'paragraph' }] },
  document_version: 1,
  source_ids: [],
  original: true,
  cover_asset_id: '',
  revision: 1,
  updated: new Date().toISOString(),
  archived: false,
  origin: { kind: 'original' },
  policy_version: 1
}

const samples = [sample1, sample2, sample3]

const visualJob = {
  id: 'visual-set:fixture',
  state: 'completed',
  detail: '隔离模拟组图完成',
  pages: samples.map((_, i) => ({ asset_id: `page-${i}`, title: ['可靠的 Agent', '执行步骤', '能力对比'][i] })),
  attempts: [{ state: 'completed' }],
  review: { pass: true, reason: '模拟检查' }
}

const state = {
  draft: JSON.parse(localStorage.getItem('fixture-draft') || JSON.stringify(initial)) as Draft,
  calls: [] as string[],
  offline: false
}

Object.assign(window, { writingFixture: state, recoveryProbe: () => recoveryProbe(state.draft) })

const ctx = {
  rest: async (path: string, options?: { method?: string; body?: Record<string, unknown> }) => {
    state.calls.push(path)

    if (state.offline) {
      throw new Error('离线测试')
    }

    if (path.startsWith('/visual-sets?')) {
      return { item: null }
    }

    if (path === '/visual-sets') {
      return visualJob
    }

    if (path.includes('/visual-sets/') && path.endsWith('/apply')) {
      return { asset_ids: visualJob.pages.map(page => page.asset_id) }
    }

    const sample = /^\/assets\/page-(\d)/.exec(path)

    if (sample) {
      return { name: '杂志样张', mime: 'image/webp', data: samples[Number(sample[1])].split(',')[1] }
    }

    if (path === '/assets') {
      return { id: 'fixture-image' }
    }

    if (path.startsWith('/assets/')) {
      return {
        name: '示例图',
        mime: 'image/png',
        data: 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j9ZkAAAAASUVORK5CYII='
      }
    }

    if (path === '/content/editor-options') {
      return { sources: [] }
    }

    if (path === '/content/cover-options') {
      return { templates: [], palettes: [] }
    }

    if (path.endsWith('/preview')) {
      return { ...projection(state.draft.document), issues: [], warnings: [], automatic_cover: true }
    }

    if (options?.method === 'PUT') {
      if (options.body?.expected_revision !== state.draft.revision) {
        throw new Error('409 conflict')
      }

      state.draft = {
        ...state.draft,
        ...options.body,
        revision: state.draft.revision + 1,
        updated: new Date().toISOString()
      }
      localStorage.setItem('fixture-draft', JSON.stringify(state.draft))

      return { id: state.draft.id, revision: state.draft.revision, updated: state.draft.updated }
    }

    return state.draft
  }
} as unknown as PluginContext

createRoot(document.getElementById('root')!).render(
  <MemoryRouter initialEntries={['/content/write?draft=fixture']}>
    <WritingPage ctx={ctx} />
  </MemoryRouter>
)
