import { inspectLoginPage } from './login-page'
import { xhsPage } from './page'
import type { Api, BrowserCommand, Guest, OperationsState } from './types'

const HOME = 'https://www.xiaohongshu.com'
const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

export async function executeBrowser(command: BrowserCommand, guest: Guest, api: Api) {
  let submitted = false
  const payload = command.payload
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
      return guest.executeJavaScript(`(${inspectLoginPage.toString()})(${JSON.stringify('xiaohongshu')})`)
    }

    return guest.executeJavaScript(`(${xhsPage.toString()})(${JSON.stringify({ operation, payload: data })})`)
  }

  const navigate = async (url: string) => {
    await check()
    const target = new URL(url)

    if (target.protocol !== 'https:' || !['www.xiaohongshu.com', 'creator.xiaohongshu.com'].includes(target.hostname)) {
      throw new Error('导航地址不属于小红书')
    }

    await guest.loadURL(url)
    await delay(1500)
  }

  try {
    await navigate(`${HOME}/explore`)
    const identity = await page('account')

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
      comment: `${HOME}/search_result?keyword=${encodeURIComponent((payload.keywords || [initial.policy.topic]).join(' '))}`,
      reply: `${HOME}/notification`,
      dm: `${HOME}/im`,
      follow: `${HOME}/user/profile/${encodeURIComponent(payload.account_id)}`
    }

    if (command.kind === 'verify') {
      if (payload.kind === 'publish' && payload.result_url) {
        await navigate(payload.result_url)

        return await page('verify-post')
      }

      if (payload.kind === 'follow') {
        await navigate(locations.follow)
        await page('click-label', { label: '粉丝' })

        return await page('interaction-result')
      }

      return { state: 'unknown', evidence: '没有可可靠核对的外部链接或消息回执，请人工核对' }
    }

    if (command.kind === 'inbox') {
      await navigate(locations[payload.kind])

      if (payload.kind === 'follow') {
        await page('click-label', { label: '粉丝' })
      }

      return await page('inventory')
    }

    if (command.kind === 'publish') {
      await navigate('https://creator.xiaohongshu.com/publish/publish?source=official')
      await page('click-label', { label: '上传图文' })

      const assets = await Promise.all(
        payload.content.asset_ids.map((id: string) => api(`/assets/${encodeURIComponent(id)}`))
      )

      await page('upload', { assets })
      await delay(3000)
      await page('fill-post', payload.content)
      await check()
      submitted = true
      await page('commit-post', payload.content)
      await delay(2000)

      return await page('post-result')
    }

    await navigate(payload.kind === 'comment' ? payload.item.url : locations[payload.kind])

    if (payload.kind === 'follow') {
      await page('click-label', { label: '粉丝' })
    }

    const prepared = await page('prepare-interaction')
    payload.before_count = prepared.before_count
    await check()
    submitted = true
    await page('commit-interaction')
    await delay(1500)

    return await page('interaction-result')
  } catch (error) {
    return {
      state: submitted ? 'unknown' : command.kind === 'account' ? 'waiting_login' : 'blocked',
      error: error instanceof Error ? error.message : String(error)
    }
  }
}
