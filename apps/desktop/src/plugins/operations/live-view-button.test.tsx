import { host } from '@hermes/plugin-sdk'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { WritableAtom } from 'nanostores'
import { afterEach, expect, it, vi } from 'vitest'

import { LiveViewButton } from './live-view-button'
import { $operationsBrowserActivity, $showOperationsBrowser, beginBrowserActivity } from './state'

vi.mock('@hermes/plugin-sdk', async importOriginal => {
  const sdk = await importOriginal<Record<string, unknown>>()
  const { atom } = await import('nanostores')

  return { ...sdk, host: { state: { requestOwner: atom({ connectionId: 'local', profile: 'one' }) } } }
})

const ownerState = host.state.requestOwner as WritableAtom<{ connectionId: string; profile: string }>

afterEach(() => {
  cleanup()
  $operationsBrowserActivity.set(null)
  $showOperationsBrowser.set(false)
  ownerState.set({ connectionId: 'local', profile: 'one' })
})

it('shows actual work beside the toggle, keeps it while hidden, and clears on completion', () => {
  render(<LiveViewButton />)
  const button = screen.getByRole('button', { name: '展开运营画面' })
  expect(button.textContent).toBe('展开运营画面')
  expect(screen.queryByLabelText('正在操作网页：发布内容')).toBeNull()
  let finish!: () => void
  act(() => { finish = beginBrowserActivity({ connectionId: 'local', profile: 'one' }, 'publish') })
  expect(screen.getByLabelText('正在操作网页：发布内容')).toBeTruthy()
  fireEvent.click(button)
  expect(button.getAttribute('aria-pressed')).toBe('true')
  expect(screen.getByRole('button', { name: '收起运营画面' }).textContent).toContain('收起运营画面')
  fireEvent.click(button)
  expect(button.getAttribute('aria-pressed')).toBe('false')
  expect(screen.getByRole('button', { name: '展开运营画面' })).toBe(button)
  expect(screen.getByLabelText('正在操作网页：发布内容')).toBeTruthy()
  act(() => finish())
  expect(screen.queryByLabelText('正在操作网页：发布内容')).toBeNull()
  act(() => $showOperationsBrowser.set(true))
  expect(screen.getByRole('button', { name: '收起运营画面' }).getAttribute('aria-pressed')).toBe('true')
  act(() => $showOperationsBrowser.set(false))
  expect(screen.getByRole('button', { name: '展开运营画面' }).getAttribute('aria-pressed')).toBe('false')
})

it('isolates owners and ignores an old task completing after another task begins', () => {
  const owner = { connectionId: 'local', profile: 'one' }
  const finishOld = beginBrowserActivity(owner, 'publish')
  render(<LiveViewButton />)
  act(() => { ownerState.set({ ...owner, profile: 'two' }) })
  expect(screen.queryByLabelText('正在操作网页：发布内容')).toBeNull()
  let finishNew!: () => void
  act(() => { finishNew = beginBrowserActivity({ ...owner, profile: 'two' }, 'verify') })
  act(() => finishOld())
  expect(screen.getByLabelText('正在操作网页：核对操作结果')).toBeTruthy()
  act(() => finishNew())
  expect(screen.queryByLabelText('正在操作网页：核对操作结果')).toBeNull()
})
