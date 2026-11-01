import type { PluginContext } from '@hermes/plugin-sdk'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { OwnedAnalysisPage } from './analysis-page'
import { AnalysisResults } from './analysis-results'
import type { AnalysisApi, AnalysisCatalog, AnalysisReport } from './analysis-types'
import { BusinessImport } from './business-import'

const template = { title: '销售订单', fields: { day: '日期', revenue: '销售额', note: '备注' }, metrics: { revenue: '销售额' } }
const catalog = { version: 2, policy: { topic: '收纳', keywords: [], modules: { analytics: true, industry: true } }, settings: { version: 0, config: { period: '7', start: '', end: '', industry: '', region: '', focus: [] } }, templates: { sales: template }, datasets: [], batches: [], reports: [], runs: [] } as unknown as AnalysisCatalog
const report = { id: 'report-1', kind: 'analytics_report', created: '2026-11-01T00:00:00Z', current: true, window: { start: '2026-10-26', end: '2026-11-01' }, detail: '已统计', model_calls: 0, sources: { counts: {}, previous: {}, trend: {}, categories: {}, keywords: {}, platforms: {} }, metrics: [{ id: 'm', name: '销售额', value: null, previous: '0', growth_percent: null, samples: 2, missing: 2, unit: 'CNY', definition: '支付金额', visibility: 'internal' }], evidence: [] } as unknown as AnalysisReport

afterEach(cleanup)

it('keeps missing metrics distinct from zero and does not imply market coverage', () => {
  render(<AnalysisResults api={vi.fn()} onSource={vi.fn()} report={report} view="content" />)
  expect(screen.getByText('缺失')).toBeTruthy()
  expect(screen.getByText(/不可比较/)).toBeTruthy()
  expect(screen.getByText(/不代表行业规模/)).toBeTruthy()
})

it('opens the cited original source and exposes internal evidence separately', () => {
  const onSource = vi.fn()
  render(<AnalysisResults api={vi.fn()} onSource={onSource} report={{ ...report, sources: undefined, findings: [{ view: 'content', title: '需求变化', dimension: '需求', text: '样本中的需求', scope: '本批资料', counter: '暂无', unknowns: '待验证', evidence_ids: ['s'], visibility: 'public' }], evidence: [{ id: 's', title: '原始资料', url: 'https://example.org/a' }] }} view="content" />)
  fireEvent.click(screen.getByText('依据、适用范围与待核实事项'))
  fireEvent.click(screen.getByRole('button', { name: '查看原始图文' }))
  expect(onSource).toHaveBeenCalledWith('s')
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
