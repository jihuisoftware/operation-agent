import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { I18nProvider, setRuntimeI18nLocale } from '@/i18n'

const { registry } = await import('@/contrib/registry')

await import('./controller')

describe('the Sessions pane tab label', () => {
  it('keeps the pane title Chinese for legacy locale requests', () => {
    const sessions = registry.getArea('panes').find(c => c.id === 'sessions')!
    const tabTitle = (sessions.data as { tabTitle: () => ReactNode }).tabTitle

    const inLocale = (locale: string) => renderToStaticMarkup(<I18nProvider>{tabTitle()}</I18nProvider>)

    expect(inLocale('zh')).toBe(inLocale('en'))
  })

  it('is joined by every other string-titled chrome pane, with a string twin for the zone menu / drag ghost', () => {
    const chrome = (id: string) =>
      registry.getArea('panes').find(c => c.id === id)!.data as {
        tabTitle: () => ReactNode
        tabTitleText: () => string
      }

    const inLocale = (id: string, locale: string) =>
      renderToStaticMarkup(<I18nProvider>{chrome(id).tabTitle()}</I18nProvider>)

    for (const id of ['terminal', 'files']) {
      expect(inLocale(id, 'zh')).toBe(inLocale(id, 'en'))
    }

    const zhSessions = inLocale('sessions', 'zh')
    const zhFiles = inLocale('files', 'zh')

    // The non-React readers (zone menu Show/Hide rows, drag ghost chip) call
    // the string twin at menu-open / drag-start, so it follows the runtime
    // locale set after registration — not the English `title` sampled at import.
    setRuntimeI18nLocale('zh')

    try {
      expect(chrome('sessions').tabTitleText()).toBe(zhSessions)
      expect(chrome('files').tabTitleText()).toBe(zhFiles)
    } finally {
      setRuntimeI18nLocale('en')
    }
  })
})
