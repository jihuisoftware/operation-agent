import type { BrowserTrace } from './browser-trace'

export type PublishAction = 'entry' | 'tab' | 'upload' | 'fill' | 'submit'

interface PublishControls {
  observe: () => Promise<PublishAction[]>
  choose: (controls: PublishAction[], turn: number) => Promise<{ action: PublishAction }>
  actions: Record<PublishAction, () => Promise<unknown>>
  trace: BrowserTrace
}

const steps = { entry: 'open_editor', tab: 'open_image_tab', upload: 'upload', fill: 'fill', submit: 'submit' }

/** Re-read controls after model latency; no model output can introduce a URL, script or content. */
export async function computerPublish({ observe, choose, actions, trace }: PublishControls) {
  const done = new Set<PublishAction>()

  const available = async () => (await observe()).filter(action => {
    if (done.has(action)) { return false }

    if (action === 'entry') { return done.size === 0 }

    if (!done.has('entry')) { return false }

    if (action === 'submit') { return done.has('fill') }

    if (action === 'fill') { return done.has('upload') }

    return !done.has('upload')
  })

  while (done.size < Object.keys(steps).length) {
    const controls = await available()

    if (!controls.length) { throw new Error('网页没有可确认的下一步发布控件') }
    const { action } = await choose(controls, done.size + 1)

    if (!controls.includes(action) || !(await available()).includes(action)) {
      throw new Error('模型选择的发布控件不可用，请核对运营画面')
    }

    await trace.step(steps[action], actions[action])

    if (action === 'submit') { return }
    done.add(action)
  }
}
