import { navigateGuest } from './browser-navigation'
import { type BrowserTrace, unrecordedTrace } from './browser-trace'
import { waitForRead } from './browser-wait'
import { inspectLoginPage } from './login-page'
import { xhsPage } from './page'
import { xhsReady } from './page-ready'
import { publicationBaseline, resolvePublication, submissionReceipt } from './publication'
import { publicationPage } from './publication-page'
import { xhsPublishControl } from './publish-control'
import type { Api, BrowserCommand, Guest, OperationsState } from './types'

const HOME = 'https://www.xiaohongshu.com'

function searchQuery(words: string[] = [], topic: string) {
  const keywords = words.map(word => word.trim()).filter(Boolean)

  return encodeURIComponent((keywords.length ? keywords : [topic]).join(' '))
}

async function evaluateGuest(guest: Guest, expression: string) {
  const result = await guest.executeJavaScript(`(() => { try { return ${expression}; } catch (error) { return { __operations_error: error instanceof Error ? error.message : String(error) }; } })()`)

  if (result?.__operations_error) { throw new Error(result.__operations_error) }

  return result
}

export async function executeBrowser(command: BrowserCommand, guest: Guest, api: Api, sleep?: (ms: number) => Promise<unknown>, trace: BrowserTrace = unrecordedTrace, worker?: string) {
  let submitted = false
  const payload = command.payload
  let baseline = payload.baseline
  let receipt: Record<string, any> = {}
  const initial = await api<OperationsState>('/policy')

  if (initial.version !== payload.policy_version) {
    return { state: 'blocked', error: '任务使用的规则已失效' }
  }

  const check = async () => {
    const current = await api<OperationsState>('/policy')

    if (
      Date.now() / 1000 > command.expires ||
      current.version !== initial.version ||
      !current.policy.enabled ||
      current.policy.paused
    ) {
      throw new Error('任务过期、规则变更或已暂停')
    }

    if (command.kind !== 'account' && !payload.account_id) {
      throw new Error('任务尚未识别登录账号，请重新执行')
    }

    if (current.policy.account_id && payload.account_id && current.policy.account_id !== payload.account_id) {
      throw new Error('账号配置与任务不匹配')
    }
  }

  const page = async (operation: string, data: Record<string, unknown> = payload) => {
    await check()
    const url = new URL(guest.getURL())

    if (url.protocol !== 'https:' || !['www.xiaohongshu.com', 'creator.xiaohongshu.com'].includes(url.hostname)) {
      throw new Error('当前网页不是任务目标平台')
    }

    if (operation === 'account') {
      return evaluateGuest(guest, `(${inspectLoginPage.toString()})(${JSON.stringify('xiaohongshu')})`)
    }

    if (operation === 'ready') {
      return evaluateGuest(guest, `(${xhsReady.toString()})(${JSON.stringify(data)}, (${xhsPublishControl.toString()}))`)
    }

    if (operation.startsWith('publication:')) {
      return evaluateGuest(guest, `(${publicationPage.toString()})(${JSON.stringify({ operation: operation.slice(12), payload: data })})`)
    }

    return evaluateGuest(guest, `(${xhsPage.toString()})(${JSON.stringify({ operation, payload: data })}, (${xhsPublishControl.toString()}))`)
  }

  const navigate = async (url: string) => {
    await check()
    const target = new URL(url)

    if (target.protocol !== 'https:' || !['www.xiaohongshu.com', 'creator.xiaohongshu.com'].includes(target.hostname)) {
      throw new Error('导航地址不属于小红书')
    }

    await navigateGuest(guest, target.href, sleep)
  }

  const ready = async (phase: string, data = payload) => {
    try {
      return await waitForRead(() => page('ready', { phase, payload: data }), result => result.ready === true, phase === 'post' ? 60000 : 15000, false, sleep)
    } catch (error) {
      throw new Error(`${phase}${data.label ? `「${data.label}」` : ''}：${error instanceof Error ? error.message : String(error)}`)
    }
  }

  const clickLabel = async (label: string) => {
    await ready('label', { label })
    await page('click-label', { label })
  }

  const publication = { read: (operation: string, data: Record<string, any>) => page(`publication:${operation}`, data), navigate, trace, sleep,
    images: (urls: string[]) => api<{ state: string; evidence: string }>('/worker/verify-images', { command_id: command.id, worker, urls }) }

  try {
    const identity = await trace.step('account', async () => {
      await navigate(`${HOME}/explore`)

      return waitForRead(() => page('account'), value => value.state !== 'unknown', 10000, true, sleep)
    })

    if (identity.state !== 'logged_in' || !identity.account_id) {
      throw new Error('未识别到登录账号，请在内嵌网页扫码登录后重新执行')
    }

    if (command.kind === 'account') {
      return identity
    }

    if (identity.account_id !== payload.account_id) {
      throw new Error('当前登录账号不匹配，已停止执行')
    }

    const locations: Record<string, string> = {
      comment: `${HOME}/search_result?keyword=${searchQuery(payload.keywords, initial.policy.topic)}`,
      reply: `${HOME}/notification`,
      dm: `${HOME}/im`,
      follow: `${HOME}/user/profile/${encodeURIComponent(payload.account_id)}`
    }

    if (command.kind === 'verify') {
      if (payload.kind === 'publish') {
        return await resolvePublication(publication, payload, payload.previous_result || { state: 'unknown', url: payload.result_url }, baseline)
      }

      if (payload.kind === 'follow') {
        await navigate(locations.follow)
        await clickLabel('粉丝')

        return await page('interaction-result')
      }

      return { state: 'unknown', evidence: '没有可可靠核对的外部链接或消息回执，请人工核对' }
    }

    if (command.kind === 'inbox') {
      return await trace.step('inventory', async () => {
        await navigate(locations[payload.kind])

        if (payload.kind === 'follow') { await clickLabel('粉丝') }
        await ready('inventory')

        return page('inventory')
      })
    }

    if (command.kind === 'publish') {
      baseline = await publicationBaseline(publication, payload)
      await trace.step('open_editor', async () => {
        await navigate('https://creator.xiaohongshu.com/publish/publish?source=official')
        await clickLabel('上传图文')
        await ready('upload')
      })

      const assets = await Promise.all(
        payload.content.asset_ids.map((id: string) => api(`/assets/${encodeURIComponent(id)}`))
      )

      await trace.step('upload', async () => {
        await page('upload', { assets })
        await ready('post')

        return { image_count: assets.length }
      })
      await trace.step('fill', async () => {
        await page('fill-post', payload.content)
        await ready('publish', payload.content)

        return page('validate-post', payload.content)
      })
      await trace.step('submit', async () => {
        await check()
        submitted = true

        return page('commit-post', payload.content)
      })
      receipt = await trace.step('receipt', () => waitForRead(() => page('post-result'), result => result.state !== 'unknown', 15000, true, sleep))

      return submissionReceipt(receipt, baseline)
    }

    await navigate(payload.kind === 'comment' ? payload.item.url : locations[payload.kind])

    if (payload.kind === 'follow') {
      await clickLabel('粉丝')
    }

    const prepared = await trace.step('prepare_interaction', async () => {
      await ready('interaction')

      return page('prepare-interaction')
    })

    payload.before_count = prepared.before_count
    await trace.step('submit_interaction', async () => {
      await check()
      submitted = true

      return page('commit-interaction')
    })

    return await trace.step('verify_interaction', () => waitForRead(() => page('interaction-result'), result => result.state === 'confirmed', 15000, true, sleep))
  } catch (error) {
    return {
      ...receipt, baseline,
      state: submitted ? (receipt.state && receipt.state !== 'unknown' ? 'submitted' : 'unknown') : command.kind === 'account' ? 'waiting_login' : 'blocked',
      error: error instanceof Error ? error.message : String(error)
    }
  }
}
