import { useState } from 'react'

import { TRANSLATIONS, useI18n } from '@/i18n'
import { normalize } from '@/lib/text'

import { Wordmark } from './wordmark'

export interface IntroProps {
  personality?: string
  seed?: number
}

const NEUTRAL_PERSONALITIES = new Set(['', 'default', 'none', 'neutral'])

export function Intro({ personality, seed }: IntroProps) {
  const [mountSeed] = useState(() => Math.floor(Math.random() * 100000))
  const { t } = useI18n()
  const rotationSeed = mountSeed + (seed ?? 0)
  const key = normalize(personality)

  const bodies =
    t.intro.stock[key] ?? (NEUTRAL_PERSONALITIES.has(key) ? t.intro.stock.none : t.intro.custom(personality || ''))

  const body = bodies[Math.abs(rotationSeed) % bodies.length] || TRANSLATIONS.zh.intro.stock.none[0]

  return (
    <div
      className="pointer-events-none flex w-full min-w-0 flex-col items-center justify-center px-0.5 py-6 text-center text-muted-foreground sm:px-6 lg:px-8"
      data-slot="aui_intro"
    >
      <div className="w-full min-w-0">
        <Wordmark className="mb-1" text="HERMES AGENT" />

        <p className="m-0 text-center leading-normal tracking-tight">{body}</p>
      </div>
    </div>
  )
}
