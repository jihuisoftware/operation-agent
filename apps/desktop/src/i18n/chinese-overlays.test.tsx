import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { I18nProvider } from './context'
import { createPluginI18n, usePluginI18n } from './plugin-i18n'
import {
  registerAppLocale,
  replaceAppLocaleSource,
  resetAppLocaleRegistry,
  resolveTranslations,
  unregisterAppLocaleSource
} from './registry'
import { translateNow } from './runtime'
import { zh } from './zh'

afterEach(() => {
  cleanup()
  resetAppLocaleRegistry()
})

it('replaces one Chinese source atomically and ignores its stale disposer', () => {
  const disposeOld = registerAppLocale('zh', { translations: { 'common.save': '旧品牌' } }, 'plugin:brand')
  const first = resolveTranslations('zh')
  expect(resolveTranslations('zh')).toBe(first)
  registerAppLocale('zh', { translations: { 'common.save': '新品牌' } }, 'plugin:brand')
  disposeOld()
  expect(translateNow('common.save')).toBe('新品牌')
  replaceAppLocaleSource('backend', [{ id: 'zh', translations: { 'common.save': '当前档案' } }])
  expect(translateNow('common.save')).toBe('当前档案')
  expect(resolveTranslations('zh')).not.toBe(first)
  unregisterAppLocaleSource('backend')
  expect(translateNow('common.save')).toBe('新品牌')
  unregisterAppLocaleSource('plugin:brand')
  expect(translateNow('common.save')).toBe(zh.common.save)
})

it('updates plugin copy after late registration and releases all copy on unload', () => {
  const disposers: Array<() => void> = []

  const plugin = createPluginI18n('content', dispose => {
    disposers.push(dispose)

    return dispose
  })

  const localeChanged = vi.fn()
  plugin.onLocaleChange(localeChanged)

  function Probe() {
    const t = usePluginI18n('content')

    return <span>{t('title')}</span>
  }

  render(
    <I18nProvider>
      <Probe />
    </I18nProvider>
  )
  expect(screen.getByText('title')).toBeTruthy()
  act(() => {
    plugin.register({ zh: { title: '内容计划' }, en: { title: 'Foreign' } })
    plugin.registerAppLocale('zh', { translations: { 'common.save': '保存计划' } })
  })
  expect(screen.getByText('内容计划')).toBeTruthy()
  expect(plugin.t('title')).toBe('内容计划')
  expect(translateNow('common.save')).toBe('保存计划')
  act(() => disposers.forEach(dispose => dispose()))
  expect(screen.getByText('title')).toBeTruthy()
  expect(translateNow('common.save')).toBe(zh.common.save)
  expect(localeChanged).not.toHaveBeenCalled()
})
