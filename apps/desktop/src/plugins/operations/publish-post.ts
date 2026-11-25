import { type BrowserExecution } from './browser-execution'
import { READINESS_MS } from './browser-timeouts'
import type { BrowserTrace } from './browser-trace'
import { waitForRead } from './browser-wait'
import { computerPublish, type PublishAction } from './computer-publish'
import type { Api, BrowserCommand, Policy } from './types'

interface PublishIO {
  execution: BrowserExecution
  api: Api
  navigate: (url: string) => Promise<void>
  clickLabel: (label: string) => Promise<void>
  page: (operation: string, data: Record<string, unknown>) => Promise<any>
  ready: (phase: string, data?: Record<string, any>) => Promise<unknown>
  trace: BrowserTrace
  worker?: string
  sleep?: (ms: number) => Promise<unknown>
}

export async function publishPost(command: BrowserCommand, method: Policy['publish_method'], io: PublishIO) {
  const { execution, api, navigate, clickLabel, page, ready, trace, worker, sleep } = io
  const content = command.payload.content
  const editor = 'https://creator.xiaohongshu.com/publish/publish?source=official'

  const upload = async () => {
    const assets = await Promise.all(content.asset_ids.map((id: string) => api(`/assets/${encodeURIComponent(id)}`)))
    await page('upload', { assets })
    await ready('post')

    return { image_count: assets.length }
  }

  const fill = async () => {
    await page('fill-post', content)
    await ready('publish', content)

    return page('validate-post', content)
  }

  const submit = async () => {
    return page('commit-post', content)
  }

  if (method === 'computer_use') {
    await navigate('https://www.xiaohongshu.com/explore')
    await computerPublish({
      observe: () => waitForRead<PublishAction[]>(() => page('publish-controls', { title: content.title }),
        controls => controls.length > 0, READINESS_MS, false, sleep, execution),
      choose: (controls, turn) => api('/worker/publish-decision', { command_id: command.id, worker, controls, turn }),
      actions: {
        // The home-page plus normally opens a popup. Follow its official destination in this account's guest.
        entry: () => navigate(editor),
        tab: async () => { await clickLabel('上传图文'); await ready('upload') },
        upload, fill, submit
      },
      trace
    })
  } else {
    await trace.step('open_editor', async () => {
      await navigate(editor)
      await clickLabel('上传图文')
      await ready('upload')
    })
    await trace.step('upload', upload)
    await trace.step('fill', fill)
    await trace.step('submit', submit)
  }
}
