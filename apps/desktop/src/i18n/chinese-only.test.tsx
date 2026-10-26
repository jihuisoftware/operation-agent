import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { type BackendLocaleRequest, syncBackendLocalePacks } from './backend-packs'
import { I18nProvider, useI18n } from './context'
import { languageOptions, resolveInitialLocale } from './languages'
import { registerPluginLocales, translatePlugin } from './plugin-i18n'
import {
  registerAppLocale,
  registeredLocaleIds,
  resetAppLocaleRegistry,
  resolveTranslations,
  unregisterAppLocaleSource
} from './registry'
import { getRuntimeI18nLocale, setRuntimeI18nLocale, translateNow } from './runtime'
import { zh } from './zh'

afterEach(() => {
  cleanup()
  resetAppLocaleRegistry()
})

it.each(['en', 'zh-hant', 'ar', 'auto', null])('uses Chinese with the legacy language %s and an English OS', saved => {
  expect(resolveInitialLocale(saved, 'en-US')).toBe('zh')
  setRuntimeI18nLocale(saved ?? 'en')
  expect(getRuntimeI18nLocale()).toBe('zh')
  expect(translateNow('common.save')).toBe(zh.common.save)
})

it('ignores foreign app and plugin packs while retaining unloadable Chinese overlays', () => {
  registerAppLocale('en', { translations: { 'common.save': 'Foreign' }, rtl: true })
  expect(registeredLocaleIds()).toEqual([])
  expect(languageOptions().map(row => row.id)).toEqual(['zh'])
  const dispose = registerAppLocale('zh', { translations: { 'common.save': '保存内容' } })
  expect(translateNow('common.save')).toBe('保存内容')
  dispose()
  expect(translateNow('common.save')).toBe(zh.common.save)
  const unload = registerPluginLocales('test', { en: { title: 'Foreign' }, zh: { title: '运营插件' } })
  expect(translatePlugin('test', 'en', 'title', [])).toBe('运营插件')
  unload()
  expect(translatePlugin('test', 'zh', 'title', [])).toBe('title')
})

it('renders Chinese document attributes and updates live Chinese copy', () => {
  function Probe() {
    const { locale, t } = useI18n()

    return <button lang={locale}>{t.common.save}</button>
  }

  render(
    <I18nProvider>
      <Probe />
    </I18nProvider>
  )
  expect(document.documentElement.lang).toBe('zh')
  expect(document.documentElement.dir).toBe('ltr')
  expect(screen.getByRole('button').textContent).toBe(zh.common.save)
  act(() => {
    registerAppLocale('zh', { translations: { 'common.save': '保存内容' } })
  })
  expect(screen.getByRole('button').textContent).toBe('保存内容')
})

it('fetches only Chinese and rejects a stale profile response', async () => {
  let resolve!: (result: unknown) => void
  let current = true

  const request = vi.fn(
    () =>
      new Promise(done => {
        resolve = done
      })
  ) as unknown as BackendLocaleRequest

  const pending = syncBackendLocalePacks(request, () => current)
  expect(request).toHaveBeenCalledWith('i18n.catalog', { lang: 'zh', surface: 'desktop' })
  current = false
  unregisterAppLocaleSource('backend')
  registerAppLocale('zh', { translations: { 'common.save': '新档案' } }, 'backend')
  resolve({ messages: { 'common.save': '旧档案' } })
  await pending
  expect(resolveTranslations('zh').common.save).toBe('新档案')
})
