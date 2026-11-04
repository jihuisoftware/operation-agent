import type { BrowserExecution } from './browser-execution'
import { BrowserExecutionError } from './browser-execution'
import { PAGE_LOAD_MS, SCRIPT_MS } from './browser-timeouts'
import type { Guest } from './types'

export async function waitForDocument(guest: Guest, execution: BrowserExecution,
  sleep: (ms: number) => Promise<unknown> = ms => new Promise(resolve => setTimeout(resolve, ms))) {
  execution.assert()

  if (!guest.isLoadingMainFrame?.()) { return }
  execution.page(new URL(guest.getURL()))
  await execution.loading(async () => {
    while (guest.isLoadingMainFrame?.()) {
      execution.assert()
      await sleep(250)
    }

    execution.assert()
    execution.page(new URL(guest.getURL()))
  }, PAGE_LOAD_MS, '页面加载（慢网络等待）')
}

export async function pageScript<T>(guest: Guest, execution: BrowserExecution, script: () => Promise<T>, label: string,
  sleep?: (ms: number) => Promise<unknown>, beforeSubmit?: () => Promise<void>) {
  do {
    await waitForDocument(guest, execution, sleep)

    if (beforeSubmit) { await beforeSubmit() }
  } while (guest.isLoadingMainFrame?.())

  execution.assert()
  const url = new URL(guest.getURL())

  if (url.protocol !== 'https:' || !['www.xiaohongshu.com', 'creator.xiaohongshu.com'].includes(url.hostname)) {
    throw new BrowserExecutionError('网页已离开任务目标平台，停止脚本执行', 'BROWSER_UNAVAILABLE')
  }

  execution.page(url)

  return execution.wait(() => {
    execution.assert()

    if (beforeSubmit) { execution.submission() }

    return script()
  }, SCRIPT_MS, true, label)
}
