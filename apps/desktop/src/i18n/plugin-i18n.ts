/** Plugin-owned Chinese messages, removed when their plugin unloads. */

import { useStore } from '@nanostores/react'
import { atom } from 'nanostores'
import { useCallback } from 'react'

import { DEFAULT_LOCALE } from './languages'
import { type AppLocaleRegistration, registerAppLocale } from './registry'
import { translateFrom } from './runtime'
import type { BundledLocale, Locale } from './types'

/** A leaf message: a literal or an interpolator (`n => `${n} left``). */
export type PluginMessageValue = string | ((...args: never[]) => string)

/** A plugin's messages for one locale — nested trees allowed, addressed by
 *  dot-path (`panel.title`). */
export interface PluginMessages {
  [key: string]: PluginMessages | PluginMessageValue
}

/** Locale → messages. Other ids remain accepted for plugin compatibility;
 *  only the Chinese bundle is registered. */
export type PluginLocaleBundles = Partial<Record<BundledLocale, PluginMessages>> & {
  [locale: Locale]: PluginMessages | undefined
}

/** Resolve a Chinese plugin message against `args`; missing messages return the key. */
export type PluginTranslate = (key: string, ...args: unknown[]) => string

export interface PluginI18n {
  /** Merge locale bundles for this plugin (call once at `register`). Returns a
   *  disposer that drops the plugin's bundles on unload/reload. */
  register: (bundles: PluginLocaleBundles) => () => void
  /** Module-level translator against the app's active locale (mirrors
   *  `translateNow`). Non-reactive — in React prefer `usePluginI18n`. */
  t: PluginTranslate
  /** Compatibility subscription: the locale is fixed, so no change events fire.
   *  The returned disposer is still tracked on plugin unload. */
  onLocaleChange: (listener: () => void) => () => void
  /** Extend Chinese app copy. Foreign locales are ignored. The overlay is
   *  attributed to this plugin and removed when it unloads. */
  registerAppLocale: (id: string, registration: AppLocaleRegistration) => () => void
}

const registry = new Map<string, PluginMessages>()

/** Bumps whenever a plugin's bundles change, so React translators re-render on
 *  a registration that lands after first paint. */
const $version = atom(0)

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function mergeMessages(base: PluginMessages, overrides: PluginMessages): PluginMessages {
  const result: PluginMessages = { ...base }

  for (const [key, value] of Object.entries(overrides)) {
    const prev = result[key]
    result[key] = isRecord(prev) && isRecord(value) ? mergeMessages(prev, value) : value
  }

  return result
}

export function registerPluginLocales(pluginId: string, bundles: PluginLocaleBundles): () => void {
  const messages = bundles.zh

  if (messages) {
    const previous = registry.get(pluginId)
    registry.set(pluginId, previous ? mergeMessages(previous, messages) : messages)
  }

  $version.set($version.get() + 1)

  return () => {
    registry.delete(pluginId)
    $version.set($version.get() + 1)
  }
}

export function translatePlugin(pluginId: string, _locale: Locale, key: string, args: unknown[]): string {
  return translateFrom(registry.get(pluginId), key, args)
}

/** Build the `ctx.i18n` door for a plugin. `track` records the disposer so the
 *  loader tears bundles down on unload (same lifecycle as `register`/`socket`). */
export function createPluginI18n(pluginId: string, track: (dispose: () => void) => () => void): PluginI18n {
  return {
    register: bundles => track(registerPluginLocales(pluginId, bundles)),
    onLocaleChange: () => track(() => {}),
    registerAppLocale: (id, registration) => track(registerAppLocale(id, registration, `plugin:${pluginId}`)),
    t: (key, ...args) => translatePlugin(pluginId, DEFAULT_LOCALE, key, args)
  }
}

/** Reactive scoped translator for React UI. Re-renders on a late bundle registration. Pass your plugin id (your default export's `id`). */
export function usePluginI18n(pluginId: string): PluginTranslate {
  const version = useStore($version)

  // `version` is the registry's change token and must key the translator's
  // identity: memoized consumers (React.memo, React Compiler output) cache
  // render slices on `t` itself, so a stable `t` over a mutated registry
  // serves stale strings after a late bundle registration.
  return useCallback(
    (key: string, ...args: unknown[]) => translatePlugin(pluginId, DEFAULT_LOCALE, key, args),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pluginId, version]
  )
}
