import { host } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { PublicationStatus } from '../action-evidence'

import { ActionBlocker } from './action-blocker'

vi.mock('@hermes/plugin-sdk', async importOriginal => ({ ...await importOriginal<Record<string, unknown>>(), host: { navigate: vi.fn() } }))
afterEach(() => { cleanup(); vi.clearAllMocks() })

it('opens the original publication in its owning topic without rerunning it', () => {
  render(<ActionBlocker result={{ blocking_action: { id: 'original', kind: 'publish', business_id: 'business', topic_id: 'other-topic' } }} />)
  fireEvent.click(screen.getByRole('button', { name: '查看原发布记录' }))
  expect(host.navigate).toHaveBeenCalledWith('/content?tab=published&record=original&business_id=business&topic_id=other-topic')
  expect(screen.getByText(/新内容可独立发布/)).toBeTruthy()
})

it('distinguishes previous evidence from the latest incomplete check', () => {
  render(<PublicationStatus result={{ publication: { execution: 'verified', platform: 'published', content: 'matched' },
    verification_stale: true, publication_inherited: ['content'], last_check: { evidence: '笔记详情尚未加载' } }} />)
  expect(screen.getByText('平台：已发布')).toBeTruthy()
  expect(screen.getByText(/不计为本次核对成功/)).toBeTruthy()
  expect(screen.getByText('内容：内容一致（历史核对）')).toBeTruthy()
  expect(screen.getByText('最近检查：笔记详情尚未加载')).toBeTruthy()
})
