import type { BrowserExecution } from './browser-execution'
import { READINESS_MS } from './browser-timeouts'
import type { BrowserTrace } from './browser-trace'
import { waitForRead } from './browser-wait'

export interface PublicationIO {
  execution?: BrowserExecution
  read: (operation: string, payload: Record<string, any>) => Promise<any>
  navigate: (url: string) => Promise<void>
  trace: BrowserTrace
  sleep?: (ms: number) => Promise<unknown>
  images: (urls: string[]) => Promise<{ state: string; evidence: string }>
}
export interface PublicationBaseline { ids: string[]; captured_at: string; account_id: string }

export async function publicationBaseline(io: PublicationIO, payload: Record<string, any>): Promise<PublicationBaseline> {
  return io.trace.step('baseline', async () => {
    await io.navigate(`https://www.xiaohongshu.com/user/profile/${encodeURIComponent(payload.account_id)}`)
    const list = await waitForRead(() => io.read('notes', payload), value => value.ready, READINESS_MS, false, io.sleep, io.execution)

    return { ids: list.notes.map((n: { id: string }) => n.id), captured_at: new Date().toISOString(), account_id: payload.account_id }
  })
}

/** Submission is never called here, including when discovery is ambiguous or delayed. */
export async function resolvePublication(io: PublicationIO, payload: Record<string, any>, receipt: Record<string, any>, baseline?: PublicationBaseline) {
  const pending = { ...receipt, state: receipt.state === 'unknown' ? 'unknown' : 'submitted', baseline,
    publication: { execution: receipt.state === 'unknown' ? 'unknown' : 'submitted', platform: 'unknown', content: 'unknown' } }

  let target = receipt.url || payload.result_url

  const isNote = (url: string) => {
    try {
      const parsed = new URL(url)

      return parsed.protocol === 'https:' && parsed.hostname === 'www.xiaohongshu.com' && /^\/explore\/[^/]+$|^\/user\/profile\/[^/]+\/[^/]+$/.test(parsed.pathname)
    } catch { return false }
  }

  if (!target || !isNote(target)) {
    if (!baseline || baseline.account_id !== payload.account_id) { return { ...pending, evidence: '缺少提交前笔记列表，不能把历史笔记认作本次发布' } }

    const found = await io.trace.step('discover', async () => {
      await io.navigate(`https://www.xiaohongshu.com/user/profile/${encodeURIComponent(payload.account_id)}`)
      const list = await waitForRead(() => io.read('notes', payload), r => r.ready && r.notes.some((n: { id: string }) => !baseline.ids.includes(n.id)), READINESS_MS, true, io.sleep, io.execution)

      const candidates = (list.notes || []).filter((n: { id: string; title: string }) => !baseline.ids.includes(n.id) &&
        (n.title === payload.content.title || normalizePrefix(payload.content.body, n.title)))

      return { candidates }
    })

    if (found.candidates.length !== 1) {
      return { ...pending, error_code: found.candidates.length ? 'AMBIGUOUS_PUBLICATION' : 'PUBLICATION_NOT_VISIBLE',
        evidence: found.candidates.length ? '出现多个相似新笔记，等待人工核对，未重复发布' : '暂未发现目标新笔记，等待后续只读核对', candidate_count: found.candidates.length }
    }

    target = found.candidates[0].url
  }

  return io.trace.step('verify_publication', async () => {
    await io.navigate(target)
    const detail = await waitForRead(() => io.read('inspect', payload), r => r.ready, READINESS_MS, true, io.sleep, io.execution)

    if (!detail.ready) { return { ...pending, url: target, evidence: '笔记详情尚未加载，等待后续核对' } }
    const textMatches = Object.values(detail.checks).every(Boolean)
    const images = textMatches ? await io.images(detail.images) : { state: 'unknown', evidence: '文本不一致，未继续核对图片' }
    const content = !textMatches ? 'mismatch' : images.state === 'matched' ? 'matched' : 'incomplete'
    let platform = detail.platform

    if (platform === 'unknown') {
      await io.navigate('https://creator.xiaohongshu.com/new/note-manager?source=official')
      const manager = await waitForRead(() => io.read('manager', { ...payload, note_id: detail.id, images: detail.images }), r => r.ready, READINESS_MS, true, io.sleep, io.execution)
      platform = manager.platform || 'unknown'
    }

    return { ...pending, url: detail.url, note_id: detail.id, actual: detail.actual, checks: { ...detail.checks, images },
      state: content === 'matched' && platform === 'published' ? 'published' : 'submitted',
      publication: { execution: 'verified', platform, content },
      evidence: content === 'mismatch' ? '实际笔记与批准内容不一致，保留原笔记并转待处理' : `作者与全文已核对；${images.evidence}；平台状态：${platform}` }
  })
}

function normalizePrefix(body: string, title: string) {
  const compact = (value: string) => value.replace(/\s+/g, '')

  return compact(title).length >= 15 && compact(body).startsWith(compact(title))
}


export function submissionReceipt(receipt: Record<string, any>, baseline: PublicationBaseline) {
  const state = receipt.state === 'unknown' ? 'unknown' : 'submitted'

  return { ...receipt, baseline, state,
    publication: { execution: state, platform: 'unknown', content: 'unknown' },
    evidence: receipt.evidence || '发布回执已取得，后续使用独立只读任务核对' }
}
