/** Chinese overlays from plugins and the active backend, layered over the bundled catalog. */

import {
  adaptStringOverrides,
  type FlatMessages,
  isRecord,
  mergeTranslations,
  type TranslationOverride,
  unflattenMessages
} from '@hermes/shared/i18n'
import { atom } from 'nanostores'

import { TRANSLATIONS } from './catalog'
import { DEFAULT_LOCALE } from './languages'
import type { Locale, Translations } from './types'

/** Who registered a language: the backend's pack layer, a plugin, or app code. */
export type AppLocaleSource = 'app' | 'backend' | `plugin:${string}`

export interface AppLocaleRegistration {
  /** Optional metadata retained for plugin compatibility. */
  endonym?: string

  englishName?: string

  rtl?: boolean
  /** The strings. Either a nested partial of `Translations` (TypeScript
   *  plugins) or a flat `{ "common.save": "Zapisz" }` map (YAML packs).
   *  Missing keys fall back to the bundled Chinese catalog. */
  translations?: FlatMessages | Record<string, unknown> | TranslationOverride<Translations>
}

/** What one source said about a language, minus the strings. */
export interface RegisteredLocaleMeta {
  endonym?: string
  englishName?: string
  rtl?: boolean
  source: AppLocaleSource
}

interface Entry extends RegisteredLocaleMeta {
  /** Nested, already unflattened; adapted against the base at resolve time. */
  translations?: Record<string, unknown>
}

let entries: Entry[] = []
let resolved: Translations | undefined

/** Bumps whenever a language is registered or dropped. Translators key on it. */
export const $appLocaleVersion = atom(0)

const bump = () => {
  resolved = undefined
  $appLocaleVersion.set($appLocaleVersion.get() + 1)
}

/** Lowercase, `_` → `-`, trimmed — the same identity the backend uses. */
export function normalizeLocaleId(id: string): string {
  return id.trim().toLowerCase().replace(/_/g, '-')
}

function toTree(translations: AppLocaleRegistration['translations'], base: Translations): Record<string, unknown> {
  if (!isRecord(translations)) {
    return {}
  }

  const flat = Object.keys(translations).some(key => key.includes('.'))

  if (!flat) {
    return translations
  }

  const leaves: FlatMessages = {}

  for (const [key, value] of Object.entries(translations)) {
    if (typeof value === 'string') {
      leaves[key] = value
    }
  }

  return unflattenMessages(leaves, base)
}

function makeEntry(registration: AppLocaleRegistration, source: AppLocaleSource): Entry {
  return {
    source,
    endonym: registration.endonym?.trim() || undefined,
    englishName: registration.englishName?.trim() || undefined,
    rtl: registration.rtl,
    translations: registration.translations ? toTree(registration.translations, TRANSLATIONS.zh) : undefined
  }
}

/**
 * Register (or replace) a language for one source. Returns a disposer that
 * drops exactly this registration; other sources' entries for the same id
 * stay. An empty id is a no-op. Registering does NOT change the active
 * locale — Desktop always uses Chinese.
 */
export function registerAppLocale(
  rawId: string,
  registration: AppLocaleRegistration,
  source: AppLocaleSource = 'app'
): () => void {
  const id = normalizeLocaleId(rawId)

  if (id !== 'zh') {
    return () => {}
  }

  const entry = makeEntry(registration, source)
  entries = entries.filter(existing => existing.source !== source)
  entries.push(entry)
  bump()

  return () => {
    const next = entries.filter(existing => existing !== entry)

    if (next.length !== entries.length) {
      entries = next
      bump()
    }
  }
}

/** Drop the copy one source registered (the backend layer on a profile
 *  switch, a plugin on unload). */
export function unregisterAppLocaleSource(source: AppLocaleSource): void {
  if (dropSource(source)) {
    bump()
  }
}

/** Atomically replace one source's Chinese overlays with one version bump,
 *  so a refresh never paints an intermediate state without that source's copy. */
export function replaceAppLocaleSource(
  source: AppLocaleSource,
  registrations: ReadonlyArray<{ id: string } & AppLocaleRegistration>
): void {
  dropSource(source)

  for (const { id: rawId, ...registration } of registrations) {
    const id = normalizeLocaleId(rawId)

    if (id === 'zh') {
      entries.push(makeEntry(registration, source))
    }
  }

  bump()
}

function dropSource(source: AppLocaleSource): boolean {
  const next = entries.filter(entry => entry.source !== source)
  const changed = next.length !== entries.length
  entries = next

  return changed
}

export function isRegisteredLocale(value: unknown): value is Locale {
  return value === DEFAULT_LOCALE && entries.length > 0
}

/** Only Chinese can have registered overlays. */
export function registeredLocaleIds(): Locale[] {
  return entries.length ? [DEFAULT_LOCALE] : []
}

/** Per-source metadata retained for plugin compatibility. */
export function registeredLocaleMeta(locale: Locale): RegisteredLocaleMeta[] {
  return (locale === DEFAULT_LOCALE ? entries : []).map(({ endonym, englishName, rtl, source }) => ({
    endonym,
    englishName,
    rtl,
    source
  }))
}

/** The Chinese catalog with source-ordered overlays, cached until registration changes. */
export function resolveTranslations(locale: Locale): Translations {
  if (locale !== DEFAULT_LOCALE) {
    return TRANSLATIONS.zh
  }

  if (resolved) {
    return resolved
  }

  let value = TRANSLATIONS.zh

  for (const entry of entries) {
    if (entry.translations) {
      value = mergeTranslations<Translations>(
        value,
        adaptStringOverrides(value, entry.translations) as TranslationOverride<Translations>
      )
    }
  }

  resolved = value

  return value
}

/** Test seam: forget every registration. */
export function resetAppLocaleRegistry(): void {
  entries = []
  bump()
}
