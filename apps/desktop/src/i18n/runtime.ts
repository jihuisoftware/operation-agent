import { isRecord } from '@hermes/shared/i18n'

import { DEFAULT_LOCALE } from './languages'
import { resolveTranslations } from './registry'
import type { Locale, Translations } from './types'

/** Walk a dot-path (`a.b.c`) into a nested message tree. */
function resolvePath(source: unknown, key: string): unknown {
  return key.split('.').reduce<unknown>((current, part) => (isRecord(current) ? current[part] : undefined), source)
}

/** A string is returned as-is, a function is called with `args`, else `null`. */
function render(value: unknown, args: unknown[]): null | string {
  if (typeof value === 'string') {
    return value
  }

  if (typeof value === 'function') {
    return (value as (...args: unknown[]) => string)(...args)
  }

  return null
}

/** Resolve a Chinese message or formatter, falling back to its key. */
export function translateFrom(source: unknown, key: string, args: unknown[]): string {
  return render(resolvePath(source, key), args) ?? key
}

/** Compatibility for callers with saved language preferences; Desktop is Chinese-only. */
export function setRuntimeI18nLocale(_locale: Locale): void {}

export function getRuntimeI18nLocale(): Locale {
  return DEFAULT_LOCALE
}

/** The merged catalog for the active runtime locale (bundled + registered
 *  packs) — for module-level code that reads whole copy blocks rather than
 *  one key. React should keep using `useI18n().t`. */
export function runtimeTranslations(): Translations {
  return resolveTranslations(DEFAULT_LOCALE)
}

export function translateNow(key: string, ...args: unknown[]): string {
  return translateFrom(runtimeTranslations(), key, args)
}
