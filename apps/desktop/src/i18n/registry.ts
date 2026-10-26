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

import { isBundledLocale, TRANSLATIONS } from './catalog'
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
  id: Locale
  /** Nested, already unflattened; adapted against the base at resolve time. */
  translations?: Record<string, unknown>
}

const entries = new Map<Locale, Entry[]>()
const resolved = new Map<Locale, { version: number; value: Translations }>()

/** Bumps whenever a language is registered or dropped. Translators key on it. */
export const $appLocaleVersion = atom(0)

const bump = () => {
  resolved.clear()
  $appLocaleVersion.set($appLocaleVersion.get() + 1)
}

/** Lowercase, `_` → `-`, trimmed — the same identity the backend uses. */
export function normalizeLocaleId(id: string): string {
  return id.trim().toLowerCase().replace(/_/g, '-')
}

function baseCatalog(id: Locale): Translations {
  return isBundledLocale(id) ? TRANSLATIONS[id] : TRANSLATIONS.zh
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

function makeEntry(id: Locale, registration: AppLocaleRegistration, source: AppLocaleSource): Entry {
  return {
    id,
    source,
    endonym: registration.endonym?.trim() || undefined,
    englishName: registration.englishName?.trim() || undefined,
    rtl: registration.rtl,
    translations: registration.translations ? toTree(registration.translations, baseCatalog(id)) : undefined
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

  const entry = makeEntry(id, registration, source)

  const list = (entries.get(id) ?? []).filter(existing => existing.source !== source)
  list.push(entry)
  entries.set(id, list)
  bump()

  return () => {
    const current = entries.get(id)

    if (!current) {
      return
    }

    const next = current.filter(existing => existing !== entry)

    if (next.length) {
      entries.set(id, next)
    } else {
      entries.delete(id)
    }

    bump()
  }
}

/** Drop every language one source registered (the backend layer on a profile
 *  switch, a plugin on unload). */
export function unregisterAppLocaleSource(source: AppLocaleSource): void {
  if (dropSource(source)) {
    bump()
  }
}

/** Atomically swap one source's whole set of languages — one version bump,
 *  so a refresh never paints an intermediate "no languages" state. */
export function replaceAppLocaleSource(
  source: AppLocaleSource,
  registrations: ReadonlyArray<{ id: string } & AppLocaleRegistration>
): void {
  dropSource(source)

  for (const { id: rawId, ...registration } of registrations) {
    const id = normalizeLocaleId(rawId)

    if (id === 'zh') {
      const list = entries.get(id) ?? []
      list.push(makeEntry(id, registration, source))
      entries.set(id, list)
    }
  }

  bump()
}

function dropSource(source: AppLocaleSource): boolean {
  let changed = false

  for (const [id, list] of entries) {
    const next = list.filter(entry => entry.source !== source)

    if (next.length !== list.length) {
      changed = true

      if (next.length) {
        entries.set(id, next)
      } else {
        entries.delete(id)
      }
    }
  }

  return changed
}

export function isRegisteredLocale(value: unknown): value is Locale {
  return typeof value === 'string' && entries.has(value)
}

/** Ids at least one source registered, in registration order. */
export function registeredLocaleIds(): Locale[] {
  return [...entries.keys()]
}

/** Per-source metadata for one id (registration order). */
export function registeredLocaleMeta(locale: Locale): RegisteredLocaleMeta[] {
  return (entries.get(locale) ?? []).map(({ endonym, englishName, rtl, source }) => ({
    endonym,
    englishName,
    rtl,
    source
  }))
}

/** The merged catalog for `locale`: bundled (or Chinese) with every
 *  registration layered on. Memoized per registry version. */
export function resolveTranslations(locale: Locale): Translations {
  const version = $appLocaleVersion.get()
  const cached = resolved.get(locale)

  if (cached && cached.version === version) {
    return cached.value
  }

  let value = baseCatalog(locale)

  for (const entry of entries.get(locale) ?? []) {
    if (entry.translations) {
      value = mergeTranslations<Translations>(
        value,
        adaptStringOverrides(value, entry.translations) as TranslationOverride<Translations>
      )
    }
  }

  resolved.set(locale, { version, value })

  return value
}

/** Test seam: forget every registration. */
export function resetAppLocaleRegistry(): void {
  entries.clear()
  bump()
}
