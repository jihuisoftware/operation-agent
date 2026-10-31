import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'

import { group } from '@/components/pane-shell/tree/model'
import { $dismissedPanes, $layoutTree } from '@/components/pane-shell/tree/store'
import { I18nProvider } from '@/i18n'
import { $browserPaneId, $previewTabs, closeRightRail, openPreview } from '@/store/preview'
import { $selectedStoredSessionId } from '@/store/session'

import { watchPreviewTiles } from '../chat/preview-tile'
import { actOnActivePreview } from '../chat/right-rail/preview-act'
import { readActivePreview, registerPreviewPageReader } from '../chat/right-rail/preview-reader'
import { registerPreviewScriptRunner } from '../chat/right-rail/preview-script-runner'

import { TitlebarControls } from './titlebar-controls'

afterEach(() => {
  cleanup()
  closeRightRail()
  $selectedStoredSessionId.set(null)
  $layoutTree.set(null)
  $dismissedPanes.set(new Set())
})

it('opens the embedded page used by agent tools and preserves it across the live-view toggle', async () => {
  watchPreviewTiles()
  $selectedStoredSessionId.set('chat')
  render(
    <MemoryRouter>
      <I18nProvider>
        <TitlebarControls onOpenSettings={() => {}} />
      </I18nProvider>
    </MemoryRouter>
  )
  fireEvent.click(screen.getByRole('button', { name: '显示浏览实时画面' }))
  expect($previewTabs.get()).toHaveLength(1)
  const tabId = $previewTabs.get()[0].id
  const url = 'https://www.xiaohongshu.com'

  // preview.open uses this same store; fake only the guest page, never launch a browser.
  act(() => {
    openPreview({ kind: 'url', label: '小红书', source: url, url })
    const paneId = $browserPaneId.get()
    $layoutTree.set(group([paneId], { active: paneId, id: 'right' }))
  })
  expect($previewTabs.get()[0].id).toBe(tabId)
  expect($browserPaneId.get()).toBe(`preview-tile:${tabId}`)
  const read = registerPreviewPageReader(tabId, async () => ({ text: '当前网页内容', title: '小红书', url }))
  const run = vi.fn(async () => JSON.stringify({ elements: [{ ref: 'search', role: 'textbox' }], success: true }))
  const unregisterRun = registerPreviewScriptRunner(tabId, run)

  try {
    expect(await readActivePreview({}, 'chat')).toMatchObject({ text: '当前网页内容', url })
    expect(await actOnActivePreview({ kind: 'elements' }, undefined, 'chat')).toMatchObject({ success: true })
    expect(run).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '隐藏浏览实时画面' }))
    expect($dismissedPanes.get().has($browserPaneId.get())).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: '显示浏览实时画面' }))
    expect(screen.getByRole('button', { name: '隐藏浏览实时画面' })).toBeTruthy()
    expect($previewTabs.get()).toHaveLength(1)
    expect($previewTabs.get()[0]).toMatchObject({ id: tabId, target: { url } })
    // Another conversation cannot read or drive this page.
    expect(await readActivePreview({}, 'other-chat')).toBeNull()
    expect(await actOnActivePreview({ kind: 'elements' }, undefined, 'other-chat')).toMatchObject({ success: false })
  } finally {
    read()
    unregisterRun()
  }
})
