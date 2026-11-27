import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeAll, expect, it, vi } from 'vitest'

import { OwnedAnalysisPage } from './analysis-page'
import { AnalysisResults } from './analysis-results'
import type { AnalysisApi, AnalysisCatalog, AnalysisReport } from './analysis-types'
import { BusinessImport } from './business-import'

const template = { title: '销售订单', fields: { day: '日期', revenue: '销售额', note: '备注' }, metrics: { revenue: '销售额' } }
const catalog = { version: 2, policy: { topic: '收纳', keywords: [], modules: { analytics: true, industry: true } }, settings: { version: 0, config: { period: '7', start: '', end: '', industry: '', region: '', focus: [] } }, templates: { sales: template }, datasets: [], batches: [], reports: [], runs: [] } as unknown as AnalysisCatalog
const report = { id: 'report-1', kind: 'analytics_report', created: '2026-11-01T00:00:00Z', current: true, window: { start: '2026-10-26', end: '2026-11-01' }, detail: '已统计', model_calls: 0, sources: { counts: {}, previous: {}, trend: {}, categories: {}, keywords: {}, platforms: {} }, metrics: [{ id: 'm', name: '销售额', value: null, previous: '0', growth_percent: null, samples: 2, missing: 2, unit: 'CNY', definition: '支付金额', visibility: 'internal' }], evidence: [] } as unknown as AnalysisReport

beforeAll(() => {
  Element.prototype.hasPointerCapture ??= () => false
  Element.prototype.setPointerCapture ??= () => undefined
  Element.prototype.releasePointerCapture ??= () => undefined
  Element.prototype.scrollIntoView ??= () => undefined
})
afterEach(cleanup)

it.each([
  ['analytics', '分析概览', '业务数据', '历史结果'],
  ['industry', '内容运营', '市场经营', '证据与历史']
] as const)('shows %s execution records only in its history tab', async (stage, first, second, history) => {
  const run = { id: 'run-1', stage, state: 'failed', started: '2026-11-01T00:00:00Z', detail: '执行失败详情' }
  const rest = vi.fn(async () => ({ ...catalog, runs: [run] }))
  const owner = { connectionId: 'connection-a', profile: 'profile-a' }
  render(<OwnedAnalysisPage ctx={{ rest } as unknown as PluginContext} owner={owner} stage={stage} />)

  fireEvent.click(await screen.findByRole('button', { name: history }))
  expect(screen.getByRole('heading', { name: '执行过程与记录' })).toBeTruthy()
  expect(screen.getByText(/执行失败详情/)).toBeTruthy()
  for (const name of [first, second]) {
    fireEvent.click(screen.getByRole('button', { name }))
    expect(screen.queryByRole('heading', { name: '执行过程与记录' })).toBeNull()
    expect(screen.queryByText(/执行失败详情/)).toBeNull()
  }
})

it.each([
  ['analytics', '历史结果'], ['industry', '证据与历史']
] as const)('switches saved %s reports by local date and then by generation time', async (stage, history) => {
  const reports = [
    { id: 'latest', created: new Date(2026, 10, 27, 0, 10).toISOString(), detail: '周五报告' },
    { id: 'afternoon', created: new Date(2026, 10, 26, 17, 35, 20).toISOString(), detail: '周四下午报告' },
    { id: 'morning', created: new Date(2026, 10, 26, 10, 12, 21).toISOString(), detail: '周四上午报告' },
    { id: 'december', created: new Date(2024, 11, 1, 12).toISOString(), detail: '年末报告' },
    { id: 'leap', created: new Date(2024, 1, 29, 12).toISOString(), detail: '闰日报告' }
  ].map(row => ({ ...report, ...row, kind: `${stage}_report` }))
  const rest = vi.fn(async (path: string) => path === '/analysis'
    ? { ...catalog, reports }
    : reports.find(row => path === `/analysis/reports/${row.id}`))
  render(<OwnedAnalysisPage ctx={{ rest } as unknown as PluginContext} owner={{ connectionId: 'a', profile: 'a' }} stage={stage} />)
  fireEvent.click(await screen.findByRole('button', { name: history }))
  await screen.findByText('周五报告')
  const date = screen.getByRole('button', { name: /报告日期/ })
  const version = screen.getByRole('combobox', { name: '当日版本' })
  fireEvent.click(date)
  expect(screen.getByRole('button', { name: '2026年11月25日' }).hasAttribute('disabled')).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '2026年11月26日' }))
  await screen.findByText('周四下午报告')
  fireEvent.keyDown(version, { key: 'ArrowDown' })
  expect(screen.getAllByRole('option').map(item => item.textContent)).toEqual(['17:35:20', '10:12:21'])
  fireEvent.click(screen.getByRole('option', { name: '10:12:21' }))
  await screen.findByText('周四上午报告')
  fireEvent.click(date)
  fireEvent.click(screen.getByRole('button', { name: '2026年11月27日' }))
  await screen.findByText('周五报告')
  expect(version.textContent).toContain('00:10:00')

  fireEvent.click(date)
  fireEvent.change(screen.getByRole('combobox', { name: '年份' }), { target: { value: '2024' } })
  fireEvent.change(screen.getByRole('combobox', { name: '月份' }), { target: { value: '2' } })
  expect(screen.getByRole('button', { name: '2024年2月28日' }).hasAttribute('disabled')).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '2024年2月29日' }))
  await screen.findByText('闰日报告')
  expect(screen.queryByRole('dialog')).toBeNull()
})

it('pages findings per industry view and starts a newly selected report on its first page', async () => {
  const reports = ['本期', '上期'].map((edition, index) => ({
    ...report, id: edition, kind: 'industry_report', created: new Date(2026, 10, 27 - index, 12).toISOString(),
    sources: undefined, findings: ['content', 'market'].flatMap(view =>
      Array.from({ length: view === 'content' ? 17 : 18 }, (_, i) => ({
        view, title: `${edition}-${view}-${i + 1}`, text: '结论', dimension: i === 16 ? '机会' : '需求',
        evidence_ids: ['source'], visibility: 'public', scope: '当前样本', counter: '', unknowns: ''
      }))),
    evidence: [{ id: 'source', title: '来源文章', url: 'https://example.org/source' }]
  }))
  const rest = vi.fn(async (path: string) => path === '/analysis' ? { ...catalog, reports }
    : reports.find(row => path === `/analysis/reports/${row.id}`))
  render(<OwnedAnalysisPage ctx={{ rest } as unknown as PluginContext} owner={{ connectionId: 'a', profile: 'a' }} stage="industry" />)

  await screen.findByText('本期-content-1')
  expect(screen.getAllByRole('article')).toHaveLength(16)
  expect(screen.queryByText('机会：证据不足')).toBeNull()
  expect(screen.getByRole('button', { name: '上一页' }).hasAttribute('disabled')).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '下一页' }))
  expect(screen.getByText('共 17 条 · 第 2 页')).toBeTruthy()
  expect(screen.getAllByRole('article')).toHaveLength(1)
  expect(screen.getByText('本期-content-17')).toBeTruthy()
  fireEvent.click(screen.getByText('依据、适用范围与待核实事项'))
  expect(screen.getByRole('button', { name: '查看原始图文' })).toBeTruthy()
  expect(screen.getByRole('button', { name: '下一页' }).hasAttribute('disabled')).toBe(true)

  fireEvent.click(screen.getByRole('button', { name: '市场经营' }))
  expect(screen.getByText('共 18 条 · 第 1 页')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '下一页' }))
  expect(screen.getByText('本期-market-18')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '上一页' }))
  expect(screen.getByText('本期-market-1')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '内容运营' }))
  expect(screen.getByText('共 17 条 · 第 1 页')).toBeTruthy()

  fireEvent.click(screen.getByRole('button', { name: '证据与历史' }))
  expect(screen.getAllByRole('article')).toHaveLength(16)
  fireEvent.click(screen.getByRole('button', { name: '下一页' }))
  expect(screen.getByText('共 17 条 · 第 2 页')).toBeTruthy()
  expect(screen.getByText('本期-content-17')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: /报告日期/ }))
  fireEvent.click(await screen.findByRole('button', { name: '2026年11月26日' }))
  await screen.findByText('上期-content-1')
  expect(screen.getAllByRole('article')).toHaveLength(16)
  expect(screen.getByRole('button', { name: '上一页' }).hasAttribute('disabled')).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '内容运营' }))
  expect(screen.getByText('共 17 条 · 第 1 页')).toBeTruthy()
  expect(screen.getByText('上期-content-1')).toBeTruthy()
})

it('reads, refreshes and switches full logs inside the selected run', async () => {
  const runs = ['first', 'second'].map(id => ({
    id, detail: id, stage: 'analytics', state: 'completed', started: '2026-11-01T00:00:00Z'
  }))
  let reads = 0
  const rest = vi.fn(async (path: string) => path === '/analysis'
    ? { ...catalog, runs }
    : { run: {}, events: [`日志 ${++reads} ${path}`], errors: [] })
  const owner = { connectionId: 'a', profile: 'a' }
  render(<OwnedAnalysisPage ctx={{ rest } as unknown as PluginContext} owner={owner} stage="analytics" />)
  fireEvent.click(await screen.findByRole('button', { name: '历史结果' }))

  for (const [index, id] of ['first', 'first', 'second'].entries()) {
    const summary = screen.getByText(new RegExp(`· ${id}$`))
    const row = summary.closest('details')!
    if (!row.open) fireEvent.click(summary)
    fireEvent.click(within(row).getByRole('button', { name: '读取完整过程' }))
    expect(await within(row).findByText(new RegExp(`日志 ${index + 1} /analysis/logs/${id}`))).toBeTruthy()
  }
  expect(screen.queryByText(/日志 .*first/)).toBeNull()
})

it('keeps missing metrics distinct from zero and does not imply market coverage', () => {
  render(<AnalysisResults api={vi.fn()} onSource={vi.fn()} report={report} view="content" />)
  expect(screen.getByText('缺失')).toBeTruthy()
  expect(screen.getByText(/不可比较/)).toBeTruthy()
  expect(screen.getByText(/不代表行业规模/)).toBeTruthy()
})

it('opens each cited article below its summary without displaying the source URL', () => {
  const onSource = vi.fn()
  const evidence = [
    { id: 'a', title: '卧室布局', summary: '床下利用抽屉收纳', url: 'https://example.org/a' },
    { id: 'b', title: '厨房收纳', summary: '橱柜使用分层隔板', url: 'https://example.org/b' }
  ]
  const finding = { view: 'content', title: '需求变化', dimension: '需求', text: '样本中的需求', scope: '本批资料',
    counter: '暂无', unknowns: '待验证', evidence_ids: evidence.map(item => item.id), visibility: 'public' }
  render(<AnalysisResults api={vi.fn()} onSource={onSource} report={{ ...report, sources: undefined, findings: [finding], evidence }} view="content" />)
  fireEvent.click(screen.getByText('依据、适用范围与待核实事项'))
  for (const item of evidence) {
    const title = screen.getByText(item.title)
    const row = within(title.closest('li')!)
    const summary = row.getByText(item.summary)
    const open = row.getByRole('button', { name: '查看原始图文' })
    expect(title.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(summary.compareDocumentPosition(open) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(row.queryByText(item.url)).toBeNull()
    fireEvent.click(open)
    expect(onSource).toHaveBeenLastCalledWith(item.id)
  }
})

it('sends explicit profile ownership and a new id for every manual run', async () => {
  const rest = vi.fn(async () => catalog)
  const owner = { connectionId: 'connection-a', profile: 'profile-a' } as any
  render(<OwnedAnalysisPage ctx={{ rest } as unknown as PluginContext} owner={owner} stage="analytics" />)
  fireEvent.click(await screen.findByRole('button', { name: '立即分析' }))
  await waitFor(() => expect(rest.mock.calls.some((args: any[]) => args[0] === '/analysis/run/analytics')).toBe(true))
  await waitFor(() => expect(screen.getByRole('button', { name: '立即分析' }).hasAttribute('disabled')).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: '立即分析' }))
  await waitFor(() => expect(rest.mock.calls.filter((args: any[]) => args[0] === '/analysis/run/analytics')).toHaveLength(2))
  const calls = rest.mock.calls.filter((args: any[]) => args[0] === '/analysis/run/analytics') as any[]
  expect(calls[0][1].owner).toBe(owner)
  expect(calls[0][1].body.request_id).not.toBe(calls[1][1].body.request_id)
})

it('requires a fresh permission preview after changing publication fields', async () => {
  const api = vi.fn(async (path: string) => {
    if (path === '/upload') { return { upload_id: 'u', sheet: 'CSV', sheets: ['CSV'], headers: ['日期', '销售额'], sample: [], suggestions: { sales: { day: '日期', revenue: '销售额' } } } }

    if (path === '/preview') { return { valid: 1, invalid: 0, errors: [], model_sample: [], sample: [], preview_token: 'preview-1' } }

    return { ok: true }
  }) as unknown as AnalysisApi

  render(<BusinessImport api={api} saved={vi.fn()} templates={{ sales: template }} />)
  fireEvent.change(screen.getByLabelText('选择 CSV / Excel'), { target: { files: [new File(['日期,销售额\n2026-11-01,10'], 'sample.csv')] } })
  fireEvent.change(await screen.findByLabelText('指标口径'), { target: { value: '支付金额' } })
  fireEvent.click(screen.getByRole('button', { name: '校验与发送范围预览' }))
  expect(await screen.findByRole('button', { name: '确认使用选项并保存' })).toBeTruthy()
  fireEvent.click(screen.getByRole('checkbox', { name: '销售额' }))
  expect(screen.queryByRole('button', { name: '确认使用选项并保存' })).toBeNull()
  expect(api).not.toHaveBeenCalledWith('/confirm', expect.anything())
})
