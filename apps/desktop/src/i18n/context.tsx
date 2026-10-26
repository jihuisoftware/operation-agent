import { applyDocumentLocale } from '@hermes/shared/i18n'
import { useStore } from '@nanostores/react'
import { createContext, type ReactNode, useContext, useEffect, useMemo } from 'react'

import { TRANSLATIONS } from './catalog'
import { DEFAULT_LOCALE } from './languages'
import { $appLocaleVersion, resolveTranslations } from './registry'
import type { Locale, Translations } from './types'

export interface I18nContextValue {
  locale: Locale
  t: Translations
}
const I18nContext = createContext<I18nContextValue>({ locale: DEFAULT_LOCALE, t: TRANSLATIONS.zh })

export function I18nProvider({ children }: { children: ReactNode }) {
  const version = useStore($appLocaleVersion)
  useEffect(() => {
    applyDocumentLocale(DEFAULT_LOCALE, false)
  }, [])

  const value = useMemo<I18nContextValue>(
    () => ({ locale: DEFAULT_LOCALE, t: resolveTranslations(DEFAULT_LOCALE) }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- overlay registration is the catalog's change token
    [version]
  )

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18nContextValue {
  return useContext(I18nContext)
}
