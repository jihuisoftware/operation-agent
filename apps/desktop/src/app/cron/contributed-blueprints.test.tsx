import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, expect, it } from 'vitest'

import { registry } from '@/contrib/registry'
import { CRON_BLUEPRINTS_AREA, type CronBlueprintContribution } from '@/sdk/cron'

import { ContributedBlueprints } from './contributed-blueprints'

afterEach(cleanup)

it('keeps an editor mounted during parent refreshes and re-homes it on Profile change', () => {
  function Editor({ profile }: { profile: string | null }) {
    const [text, setText] = useState(profile || '')

    return <input aria-label="草稿" onChange={e => setText(e.target.value)} value={text} />
  }

  const dispose = registry.register({
    id: 'test:blueprints',
    area: CRON_BLUEPRINTS_AREA,
    data: { render: ({ owner }) => <Editor profile={owner.profile} /> } satisfies CronBlueprintContribution
  })

  try {
    const { rerender } = render(<ContributedBlueprints profile="one" view="blueprints" />)
    fireEvent.change(screen.getByLabelText('草稿'), { target: { value: '未保存' } })
    rerender(<ContributedBlueprints profile="one" view="blueprints" />)
    expect((screen.getByLabelText('草稿') as HTMLInputElement).value).toBe('未保存')
    rerender(<ContributedBlueprints profile="two" view="blueprints" />)
    expect((screen.getByLabelText('草稿') as HTMLInputElement).value).toBe('two')
  } finally {
    dispose()
  }
})
