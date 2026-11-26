import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { registry } from '@/contrib/registry'
import { COVER_DESIGNER_AREA, type CoverDesignerProps, type PluginContext } from '@/sdk'

import { DesignerSlot } from '../plugins/operations/designer-slot'

afterEach(cleanup)

it('mounts an installed panel, binds its request to the displayed revision and removes it on unload', async () => {
  const rest = vi.fn().mockResolvedValue({})

  const mounted = render(<DesignerSlot ctx={{ rest } as unknown as PluginContext} refresh={vi.fn()}
    row={{ id: 'note', title: '旅行', content_revision: 'v1', policy_version: 7 }} />)

  expect(mounted.container.textContent).toBe('')

  const data = { render: (props: CoverDesignerProps) => <button onClick={() => void props.start({
    request_id: 'preview', mode: 'ai', title: props.title, subtitle: '', style: '插画', x: .5, y: .5
  })}>生成候选</button> }

  let dispose!: () => void
  act(() => { dispose = registry.register({ id: 'cover-designer:test', source: 'plugin:cover-designer', area: COVER_DESIGNER_AREA, data }) })
  fireEvent.click(screen.getByRole('button', { name: '生成候选' }))
  await waitFor(() => expect(rest).toHaveBeenCalledWith('/cover-designer', expect.objectContaining({
    body: expect.objectContaining({ kind: 'content', origin_id: 'note', revision: 'v1', version: 7, title: '旅行' })
  })))
  act(dispose)
  expect(mounted.container.textContent).toBe('')
})
