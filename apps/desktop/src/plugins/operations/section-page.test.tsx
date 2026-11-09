import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'

import { SectionPage } from './section-page'

vi.mock('@hermes/plugin-sdk', async importOriginal => {
  const sdk = await importOriginal<Record<string, unknown>>()
  const { atom } = await import('nanostores')

  return { ...sdk, host: { state: { requestOwner: atom({ connectionId: 'local', profile: 'work' }) } } }
})
vi.mock('./content-library', () => ({ ContentLibrary: () => <p>内容列表</p> }))
afterEach(cleanup)

function Location() { return <output aria-label="当前地址">{useLocation().search}</output> }

it('clears the record filter when switching tabs while retaining business ownership', async () => {
  render(<MemoryRouter initialEntries={['/content?tab=published&record=action-id&business_id=b&topic_id=t']}>
    <SectionPage ctx={{ rest: vi.fn() } as unknown as PluginContext} section="content" /><Location />
  </MemoryRouter>)
  await screen.findByText('内容列表')
  fireEvent.click(screen.getByRole('button', { name: '待审核' }))
  const query = new URLSearchParams(screen.getByLabelText('当前地址').textContent!)
  expect(query.get('tab')).toBe('drafts')
  expect(query.has('record')).toBe(false)
  expect(query.get('business_id')).toBe('b')
  expect(query.get('topic_id')).toBe('t')
})
