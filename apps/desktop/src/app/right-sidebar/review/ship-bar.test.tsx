import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import type { HermesReviewFile } from '@/global'
import { I18nProvider } from '@/i18n'
import { $reviewFiles, $reviewScope, $reviewShipInfo } from '@/store/review'

import { ReviewShipBar } from './ship-bar'

const file = (path: string): HermesReviewFile => ({
  added: 1,
  path,
  removed: 0,
  staged: false,
  status: 'M'
})

function renderBar() {
  return render(
    <I18nProvider>
      <ReviewShipBar />
    </I18nProvider>
  )
}

describe('ReviewShipBar', () => {
  beforeEach(() => {
    $reviewFiles.set([file('a.ts')])
    $reviewShipInfo.set({ ghReady: false, pr: null })
    $reviewScope.set('uncommitted')
  })

  afterEach(() => {
    cleanup()
    $reviewFiles.set([])
    $reviewScope.set('uncommitted')
  })

  it('renders the commit bar for the uncommitted scope', () => {
    renderBar()

    expect(screen.getByText('提交')).toBeTruthy()
  })

  it('renders a read-only note for the branch scope (no working-tree actions)', () => {
    $reviewScope.set('branch')

    const { container } = renderBar()

    // The bar itself must be gone (no Commit button), replaced by the note
    // explaining why — not silently vanishing.
    expect(screen.queryByText('提交')).toBeNull()
    expect(screen.getByText(/只读视图 — 暂存、还原和提交操作仅适用于“未提交”/)).toBeTruthy()
    expect(container.firstChild).not.toBeNull()
  })

  it('renders nothing for the uncommitted scope when there are no files', () => {
    $reviewFiles.set([])

    const { container } = renderBar()

    expect(container.firstChild).toBeNull()
  })
})
