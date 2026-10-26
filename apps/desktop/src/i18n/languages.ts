import type { AppLocaleSource } from './registry'
import type { BundledLocale, Locale } from './types'

export const DEFAULT_LOCALE: BundledLocale = 'zh'
export const LOCALE_OPTIONS = [
  { id: 'zh', name: '简体中文', englishName: 'Simplified Chinese', configValue: 'zh' }
] as const

export interface LanguageOption {
  id: Locale
  endonym: string
  englishName?: string
  rtl: boolean
  source: 'bundled' | AppLocaleSource
}

export function localeMeta(_locale: Locale): Pick<LanguageOption, 'endonym' | 'englishName' | 'rtl'> {
  return { endonym: '简体中文', englishName: 'Simplified Chinese', rtl: false }
}

export function isRtlLocale(_locale: Locale): boolean {
  return false
}

export function languageOptions(): LanguageOption[] {
  return [{ id: DEFAULT_LOCALE, ...localeMeta(DEFAULT_LOCALE), source: 'bundled' }]
}

export function isLocale(value: unknown): value is Locale {
  return value === DEFAULT_LOCALE
}

/** Old saved languages and OS preferences all resolve to the product's Chinese UI. */
export function normalizeLocale(_value: unknown): Locale {
  return DEFAULT_LOCALE
}

export function isSupportedLocaleValue(value: unknown): boolean {
  return (
    typeof value === 'string' &&
    ['zh', 'zh-cn', 'zh-hans', 'zh-hans-cn'].includes(value.trim().toLowerCase().replace(/_/g, '-'))
  )
}

export function osPreferredLocale(_tag: string | null | undefined): Locale {
  return DEFAULT_LOCALE
}

export function resolveInitialLocale(_saved: string | null | undefined, _osLocale: string | null | undefined): Locale {
  return DEFAULT_LOCALE
}

export function localeConfigValue(_locale: Locale): string {
  return DEFAULT_LOCALE
}
