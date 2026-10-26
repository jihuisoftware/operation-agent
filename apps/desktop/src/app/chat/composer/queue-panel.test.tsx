import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '@/i18n/context'
import type { QueuedPromptEntry } from '@/store/composer-queue'

import { QueuePanel } from './queue-panel'

const entry = (id: string, text: string): QueuedPromptEntry => ({
  attachments: [],
  id,
  queuedAt: Date.now(),
  text
})

function renderPanel(entries: QueuedPromptEntry[], onDiscardLost?: (id: string) => void) {
  return render(
    <I18nProvider>
      <QueuePanel
        busy={false}
        editingId={null}
        entries={entries}
        onDelete={vi.fn()}
        onDiscardLost={onDiscardLost}
        onEdit={vi.fn()}
        onResume={vi.fn()}
        onSendNow={vi.fn()}
        parked={false}
      />
    </I18nProvider>
  )
}

afterEach(cleanup)

// The panel's StatusSection starts collapsed; tests read the entries, so open it.
async function renderExpandedPanel(entries: QueuedPromptEntry[]) {
  const view = renderPanel(entries)

  fireEvent.click(await view.findByRole('button', { name: /排队/ }))

  return view
}

// #45664: a long queued prompt was only ever readable as one truncated line
// (or by loading it back into the composer). Long and multiline previews now
// carry an expand/collapse toggle that reveals the full text in place.
describe('QueuePanel expandable previews', () => {
  it('offers expansion for long and multiline entries but not short ones', async () => {
    await renderExpandedPanel([
      entry('short', 'Quick note'),
      entry('long', 'A'.repeat(200)),
      entry('multiline', 'First line\nSecond line')
    ])

    await screen.findByText('Quick note')

    // Exactly the two long/multiline entries get a toggle, not the short one.
    expect(screen.getAllByRole('button', { name: /展开/ })).toHaveLength(2)
  })

  it('expands an entry to its full text and collapses it back', async () => {
    const text = `${'A'.repeat(200)}\nlast line`
    await renderExpandedPanel([entry('long', text)])

    // The DOM keeps the newline in textContent; findByText normalizes
    // whitespace, so locate the <p> by exact textContent instead.
    expect(
      await screen.findByText((_, element) => element?.tagName === 'P' && element.textContent === text)
    ).toBeTruthy()

    const toggle = screen.getByRole('button', { name: /展开/ })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')

    fireEvent.click(toggle)

    const collapse = screen.getByRole('button', { name: /收起/ })
    expect(collapse.getAttribute('aria-expanded')).toBe('true')

    fireEvent.click(collapse)
    expect(screen.getByRole('button', { name: /展开/ }).getAttribute('aria-expanded')).toBe('false')
  })
})

// #134889 NF2: after the gateway is killed mid-turn, owner recovery fences the turn `unknown` and
// pauses the FIFO behind it. The Discard choice lived inside the collapsed queue section, so the
// chat showed only "1 Queued" (then "2 Queued" for a follow-up) with no reason and no action.
describe('QueuePanel lost turn', () => {
  it('shows the lost turn and its Discard without expanding, and names the pause', async () => {
    const onDiscardLost = vi.fn()
    renderPanel(
      [{ ...entry('lost', 'doomed turn'), serverStatus: 'unknown' }, entry('next', 'follow up')],
      onDiscardLost
    )

    expect(await screen.findByText('重启期间该轮次已丢失')).toBeTruthy()
    expect(screen.getByRole('button', { name: /2 条排队 — 已暂停/ })).toBeTruthy()
    // Only the lost row is previewed while collapsed; the healthy follow-up stays inside the section.
    expect(screen.queryByText('follow up')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '丢弃' }))
    expect(onDiscardLost).toHaveBeenCalledWith('lost')
  })

  it('opens when a queued row turns lost after the panel mounted', async () => {
    const view = renderPanel([entry('a', 'first')])
    expect(view.queryByText('重启期间该轮次已丢失')).toBeNull()
    view.rerender(
      <I18nProvider>
        <QueuePanel
          busy={false}
          editingId={null}
          entries={[{ ...entry('a', 'first'), serverStatus: 'unknown' }]}
          onDelete={vi.fn()}
          onDiscardLost={vi.fn()}
          onEdit={vi.fn()}
          onResume={vi.fn()}
          onSendNow={vi.fn()}
          parked={false}
        />
      </I18nProvider>
    )
    expect(await screen.findByText('重启期间该轮次已丢失')).toBeTruthy()
  })
})
