import { pageScript } from './browser-document'
import { BrowserExecution, BrowserExecutionError } from './browser-execution'
import { openInteraction, openInventory } from './browser-inventory'
import { navigateGuest } from './browser-navigation'
import { BACKEND_MS, READINESS_MS } from './browser-timeouts'
import { type BrowserTrace, unrecordedTrace } from './browser-trace'
import { BrowserReadinessError, waitForRead } from './browser-wait'
import { xhsInteractionDom } from './interaction-dom'
import { confirmLogin } from './login-evidence'
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
  const result = await guest.executeJavaScript(
    `(() => { try { return ${expression}; } catch (error) { return { __operations_error: error instanceof Error ? error.message : String(error) }; } })()`
  )

  if (result?.__operations_error) {
    throw new Error(result.__operations_error)
  }

  return result
}

export async function executeBrowser(
  command: BrowserCommand,
  guest: Guest,
  request: Api,
  sleep?: (ms: number) => Promise<unknown>,
  trace: BrowserTrace = unrecordedTrace,
  worker?: string,
  context?: BrowserExecution
) {
  const execution = context || new BrowserExecution(command, guest)

  try { return await executeCommand(command, guest, request, trace, execution, sleep, worker) } catch (error) {
    return execution.failure(error)
  } finally { if (!context) { execution.finish() } }
}

async function executeCommand(command: BrowserCommand, guest: Guest, request: Api, trace: BrowserTrace,
  execution: BrowserExecution, sleep?: (ms: number) => Promise<unknown>, worker?: string) {
  const api: Api = (path, body, method) => execution.wait(() => request(path, body, method), path === '/worker/verify-images' ? 60000 : BACKEND_MS, false, `后台接口 ${path}`)
  const payload = command.payload
  let baseline = payload.baseline
  let receipt: Record<string, any> = {}
  const initial = await api<OperationsState>('/policy')

  if (initial.version !== payload.policy_version) {
    return { state: 'blocked', error: '任务使用的规则已失效', submitted: false, dispatch_state: execution.dispatchState }
  }

  const check = async () => {
    execution.assert()
    const current = await api<OperationsState>('/policy')
    execution.block(current.execution_block)
    execution.assert()

    if (current.web_held) { throw new BrowserReadinessError('网页控制已暂停，当前动作尚未提交', 'CONTROL_PAUSED') }

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
      throw new BrowserExecutionError('账号配置与任务不匹配', 'ACCOUNT_CHANGED')
    }
  }

  const page = async (operation: string, data: Record<string, unknown> = payload) => {
    await check()
    const url = new URL(guest.getURL())
    execution.page(url)

    if (url.protocol !== 'https:' || !['www.xiaohongshu.com', 'creator.xiaohongshu.com'].includes(url.hostname)) {
      throw new Error('当前网页不是任务目标平台')
    }

    const identity = await confirmLogin(
      () => pageScript(guest, execution, () => evaluateGuest(guest, `(${inspectLoginPage.toString()})(${JSON.stringify('xiaohongshu')})`), '网页脚本：登录识别', sleep),
      () => guest.getURL(), execution, operation === 'account', sleep
    )

    if (operation === 'account') { return identity }

    execution.observe(identity.state, identity.account_id)
    execution.assert()

    if (operation === 'ready') {
      return pageScript(guest, execution, () => evaluateGuest(
        guest,
        `(${xhsReady.toString()})(${JSON.stringify(data)}, (${xhsPublishControl.toString()}), (${xhsInteractionDom.toString()}))`
      ), `网页脚本：${data.phase}就绪`, sleep)
    }

    if (operation.startsWith('publication:')) {
      return pageScript(guest, execution, () => evaluateGuest(
        guest,
        `(${publicationPage.toString()})(${JSON.stringify({ operation: operation.slice(12), payload: data })})`
      ), `网页脚本：${operation}`, sleep)
    }

    return pageScript(guest, execution, () => evaluateGuest(
      guest,
      `(${xhsPage.toString()})(${JSON.stringify({ operation, payload: data })}, (${xhsPublishControl.toString()}), (${xhsInteractionDom.toString()}))`
    ), `网页脚本：${operation}`, sleep, ['commit-post', 'commit-interaction'].includes(operation) ? check : undefined)
  }

  const navigate = async (url: string) => {
    await check()
    const target = new URL(url)

    if (target.protocol !== 'https:' || !['www.xiaohongshu.com', 'creator.xiaohongshu.com'].includes(target.hostname)) {
      throw new Error('导航地址不属于小红书')
    }

    await navigateGuest(guest, target.href, sleep, execution)
  }

  const ready = async (phase: string, data = payload) => {
    let reason = ''

    try {
      return await waitForRead(
        async () => {
          const result = await page('ready', { phase, payload: data })
          reason = result.reason || ''

          if (result.unavailable) { throw new BrowserReadinessError(reason, 'PAGE_UNAVAILABLE') }

          return result
        },
        result => result.ready === true,
        READINESS_MS,
        false,
        sleep,
        execution
      )
    } catch (error) {
      const message = `${phase}${data.label ? `「${data.label}」` : ''}：${error instanceof Error ? error.message : String(error)}${reason ? `；${reason}` : ''}`

      if (error instanceof BrowserExecutionError) { throw new BrowserExecutionError(message, error.code) }

      if (error instanceof BrowserReadinessError) { throw new BrowserReadinessError(message, error.code) }
      throw new Error(message)
    }
  }

  const clickLabel = async (label: string) => {
    await ready('label', { label })
    await page('click-label', { label })
  }

  const publication = {
    read: (operation: string, data: Record<string, any>) => page(`publication:${operation}`, data),
    navigate,
    trace,
    execution,
    sleep,
    images: (urls: string[]) =>
      api<{ state: string; evidence: string }>('/worker/verify-images', { command_id: command.id, worker, urls })
  }

  try {
    const identity = await trace.step('account', async () => {
      await navigate(`${HOME}/explore`)

      return page('account')
    })

    execution.observe(identity.state, identity.account_id)
    execution.assert()

    if (identity.state !== 'logged_in' || !identity.account_id) {
      throw new BrowserExecutionError('登录状态仍未确认，请等待页面加载完成后手动继续', 'BROWSER_UNAVAILABLE')
    }

    if (command.kind === 'account' && !payload.readonly_inventory) {
      return identity
    }

    if (command.kind === 'account' && payload.readonly_inventory !== 'comment') {
      throw new Error('未知的只读网页检查类型')
    }

    if (command.kind !== 'account' && identity.account_id !== payload.account_id) {
      throw new BrowserExecutionError('当前登录账号不匹配，已停止执行', 'ACCOUNT_CHANGED')
    }

    const locations: Record<string, string> = {
      comment: `${HOME}/search_result?keyword=${searchQuery(payload.keywords, initial.policy.topic)}`,
      reply: `${HOME}/notification`,
      follow: `${HOME}/user/profile/${encodeURIComponent(payload.account_id)}`
    }

    if (command.kind === 'account' && payload.readonly_inventory === 'comment') {
      return trace.step('inventory', async () => {
        const readOnly = { ...payload, kind: 'comment', account_id: identity.account_id }
        await openInventory(readOnly, { navigate, page: operation => page(operation, readOnly),
          ready: phase => ready(phase, readOnly), clickLabel, locations })
        const items = await page('inventory', readOnly)

        return { ...identity, ...items, probe: 'account_and_search' }
      })
    }

    if (command.kind === 'verify') {
      if (payload.kind === 'publish') {
        return await resolvePublication(
          publication,
          payload,
          payload.previous_result || { state: 'unknown', url: payload.result_url },
          baseline
        )
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
        await openInventory(payload, { navigate, page, ready, clickLabel, locations })

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

        return page('commit-post', payload.content)
      })
      receipt = await trace.step('receipt', () =>
        waitForRead(
          () => page('post-result'),
          result => result.state !== 'unknown',
          READINESS_MS,
          true,
          sleep,
          execution
        )
      )

      return submissionReceipt(receipt, baseline)
    }

    await trace.step('open_interaction', () => openInteraction(payload, { navigate, page, ready, clickLabel, locations }))

    const prepared = await trace.step('prepare_interaction', async () => {
      await ready('interaction')

      return page('prepare-interaction')
    })

    payload.before_count = prepared.before_count
    await trace.step('submit_interaction', async () => {
      await check()

      return page('commit-interaction')
    })

    return await trace.step('verify_interaction', () =>
      waitForRead(
        () => page('interaction-result'),
        result => result.state === 'confirmed',
        READINESS_MS,
        true,
        sleep,
        execution
      )
    )
  } catch (error) {
    return failureReceipt(execution, error, receipt, baseline)
  }
}

function failureReceipt(execution: BrowserExecution, error: unknown, receipt: Record<string, any>, baseline: unknown) {
  const result = execution.failure(error)

  if (result.submitted && receipt.state && receipt.state !== 'unknown') { result.state = 'submitted' }

  return { ...receipt, baseline, ...result, error_code: error instanceof BrowserReadinessError ? error.code : result.error_code }
}
