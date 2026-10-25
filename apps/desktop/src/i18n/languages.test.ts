import { describe, expect, it } from 'vitest'

import { TRANSLATIONS } from './catalog'
import { DEFAULT_LOCALE, isLocale, isSupportedLocaleValue, LOCALE_OPTIONS, normalizeLocale } from './languages'

describe('desktop i18n languages', () => {
  it('normalizes supported locale aliases', () => {
    expect(normalizeLocale('en')).toBe('en')
    expect(normalizeLocale('EN-US')).toBe('en')
    expect(normalizeLocale('zh')).toBe('zh')
    expect(normalizeLocale('zh-CN')).toBe('zh')
    expect(normalizeLocale('zh-Hans')).toBe('zh')
    expect(normalizeLocale(' zh_hans_cn ')).toBe('zh')
  })

  it('falls back to English for empty or unsupported values', () => {
    expect(normalizeLocale(null)).toBe(DEFAULT_LOCALE)
    expect(normalizeLocale('')).toBe(DEFAULT_LOCALE)
    for (const retired of ['it', 'ja', 'de-DE', 'zh-Hant', 'ar']) {
      expect(normalizeLocale(retired)).toBe(DEFAULT_LOCALE)
      expect(isSupportedLocaleValue(retired)).toBe(false)
    }
  })

  it('distinguishes exact locale ids from supported config aliases', () => {
    expect(isSupportedLocaleValue('zh-CN')).toBe(true)
    expect(isSupportedLocaleValue('it')).toBe(false)
    expect(isLocale('zh-CN')).toBe(false)
    expect(isLocale('zh')).toBe(true)
  })

  it('round-trips every picker option through its display.language value to a registered catalog', () => {
    for (const option of LOCALE_OPTIONS) {
      expect(normalizeLocale(option.configValue)).toBe(option.id)
      expect(TRANSLATIONS[option.id]).toBeDefined()
    }

    expect(Object.keys(TRANSLATIONS).sort()).toEqual(LOCALE_OPTIONS.map(option => option.id).sort())
  })
})
