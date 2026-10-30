import { type AppLocaleRegistration, type LanguageOption, languageOptions, registerAppLocale } from '@/i18n'

/** Extend Chinese UI copy at runtime. A registration is a partial catalog,
 *  nested like `zh.ts` or using dotted keys (`{ "common.save": "保存计划" }`).
 *  Missing keys use the bundled Chinese catalog; string overrides of
 *  functions support positional `{0}`/`{1}` formatting. Foreign ids are ignored.
 *
 *  Prefer `ctx.i18n.registerAppLocale` inside `register(ctx)`: same call,
 *  attributed to the plugin and disposed on unload. This host form is for
 *  code with no ctx in reach; hand its disposer to `ctx.onDispose`. */
export const i18nHost = {
  /** Register (or replace) app-owned Chinese copy; returns its disposer. */
  registerAppLocale: (id: string, registration: AppLocaleRegistration): (() => void) =>
    registerAppLocale(id, registration, 'app'),

  /** The single supported language: Simplified Chinese. */
  languageOptions: (): LanguageOption[] => languageOptions()
}
