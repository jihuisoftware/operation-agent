import type { ReactNode } from 'react'

import { useI18n } from './context'
import type { Translations } from './types'

/** Resolve pane titles at render time so late Chinese overlays update existing tabs. */
export function LocalizedTabTitle({ select }: { select: (t: Translations) => ReactNode }) {
  const { t } = useI18n()

  return <>{select(t)}</>
}
