import { LOCALE_ENDONYMS, RTL_LOCALES } from '@hermes/shared/i18n'

import { normalize } from '@/lib/text'

import { isBundledLocale } from './catalog'
import {
  type AppLocaleSource,
  isRegisteredLocale,
  normalizeLocaleId,
  registeredLocaleIds,
  registeredLocaleMeta
} from './registry'
import type { BundledLocale, Locale } from './types'

export const DEFAULT_LOCALE: BundledLocale = 'en'

export const LOCALE_OPTIONS = [
  {
    id: 'en',
    name: LOCALE_ENDONYMS.en,
    englishName: 'English',
    configValue: 'en'
  },
  {
    id: 'zh',
    name: LOCALE_ENDONYMS.zh,
    englishName: 'Simplified Chinese',
    configValue: 'zh'
  }
] as const satisfies readonly { configValue: string; englishName: string; id: BundledLocale; name: string }[]

export interface LanguageOption {
  id: Locale
  /** Native name shown in the picker (`Polski`). */
  endonym: string
  /** Search-only English name; absent for a registered language that gave none. */
  englishName?: string
  rtl: boolean
  source: 'bundled' | AppLocaleSource
}

const bundledOption = new Map<string, (typeof LOCALE_OPTIONS)[number]>(
  LOCALE_OPTIONS.map(option => [option.id, option])
)

/** Endonym / search name / direction for one id: registry (last word wins)
 *  → bundled picker table → shared endonyms → the id itself. */
export function localeMeta(locale: Locale): Pick<LanguageOption, 'endonym' | 'englishName' | 'rtl'> {
  const registered = registeredLocaleMeta(locale).reverse()
  const bundled = bundledOption.get(locale)
  const rtlEntry = registered.find(entry => entry.rtl !== undefined)

  return {
    endonym:
      registered.find(entry => entry.endonym)?.endonym ??
      bundled?.name ??
      (LOCALE_ENDONYMS as Record<string, string>)[locale] ??
      locale,
    englishName: registered.find(entry => entry.englishName)?.englishName ?? bundled?.englishName,
    rtl: rtlEntry ? Boolean(rtlEntry.rtl) : RTL_LOCALES.has(locale)
  }
}

export function isRtlLocale(locale: Locale): boolean {
  return localeMeta(locale).rtl
}

// The endonym (native name) is what the picker shows so users recognize their
// language regardless of the current UI language. No country flags: languages
// are not countries. `englishName` is search-only (not shown) so an English
// speaker can type "english"/"chinese" to filter the list.
/** Every selectable language: bundled ∪ registered (plugin packs, backend
 *  `i18n.languages`). Bundled keep their curated picker order; registered-only
 *  ids follow, sorted. */
export function languageOptions(): LanguageOption[] {
  const options: LanguageOption[] = LOCALE_OPTIONS.map(option => ({
    id: option.id,
    ...localeMeta(option.id),
    source: 'bundled'
  }))

  for (const id of registeredLocaleIds()
    .filter(id => !isBundledLocale(id))
    .sort()) {
    options.push({ id, ...localeMeta(id), source: registeredLocaleMeta(id)[0]?.source ?? 'app' })
  }

  return options
}

const LOCALE_ALIASES: Record<string, BundledLocale> = {
  en: 'en',
  'en-us': 'en',
  en_us: 'en',
  zh: 'zh',
  'zh-cn': 'zh',
  zh_cn: 'zh',
  'zh-hans': 'zh',
  zh_hans: 'zh',
  'zh-hans-cn': 'zh',
  zh_hans_cn: 'zh'
}

/** A language the app can render right now: bundled or registered. Aliases
 *  (`zh-CN`) are not ids — see `isSupportedLocaleValue`. */
export function isLocale(value: unknown): value is Locale {
  return isBundledLocale(value) || isRegisteredLocale(value)
}

/** Alias table first (`zh-CN` → `zh`), then any registered id as-is
 *  (lowercased, `_` → `-`), else English. */
export function normalizeLocale(value: unknown): Locale {
  if (typeof value !== 'string') {
    return DEFAULT_LOCALE
  }

  const alias = LOCALE_ALIASES[normalize(value)]

  if (alias) {
    return alias
  }

  const id = normalizeLocaleId(value)

  return isRegisteredLocale(id) ? id : DEFAULT_LOCALE
}

export function isSupportedLocaleValue(value: unknown): boolean {
  return (
    typeof value === 'string' &&
    (LOCALE_ALIASES[normalize(value)] != null || isRegisteredLocale(normalizeLocaleId(value)))
  )
}

/** OS tags can include regions absent from the picker aliases, such as en-GB. */
export function osPreferredLocale(tag: string | null | undefined): Locale | null {
  if (!tag) {
    return null
  }

  const exact = LOCALE_ALIASES[normalize(tag)]

  if (exact) {
    return exact
  }

  const base = tag.split(/[-_]/)[0]

  return (base && LOCALE_ALIASES[normalize(base)]) || null
}

/** An explicit choice must win even when it differs from the OS language. */
export function resolveInitialLocale(saved: string | null | undefined, osLocale: string | null | undefined): Locale {
  if (isSupportedLocaleValue(saved)) {
    return normalizeLocale(saved)
  }

  return osPreferredLocale(osLocale) ?? DEFAULT_LOCALE
}

/** The `display.language` value for a picker choice — the bundled option's
 *  config value, or the registered id itself. */
export function localeConfigValue(locale: Locale): string {
  return bundledOption.get(locale)?.configValue ?? (isRegisteredLocale(locale) ? locale : DEFAULT_LOCALE)
}
