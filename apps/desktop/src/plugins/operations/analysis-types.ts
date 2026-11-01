import type { Policy } from './types'

export interface AnalysisConfig {
  period: string
  start: string
  end: string
  industry: string
  region: string
  focus: string[]
}
export interface Sharing {
  model_mode: string
  detail_fields: string[]
  public_metrics: string[]
}
export interface BusinessConfig {
  template: string
  mapping: Record<string, string>
  date_format: string
  semantics: string
  currency: string
  definition: string
  dedupe: boolean
}
export interface Dataset {
  id: string
  version: number
  name: string
  active: boolean
  scope_topic: string
  config: BusinessConfig
  sharing: Sharing
  batches: string[]
}
export interface Template { title: string; metrics: Record<string, string>; fields: Record<string, string> }
export interface AnalysisRun { id: string; stage: string; state: string; started: string; ended: string | null; detail: string }
export interface ReportSummary { id: string; kind: string; created: string; detail: string; state: string; window: Record<string, string> }
export interface AnalysisCatalog {
  version: number
  policy: Policy
  settings: { version: number; config: AnalysisConfig }
  datasets: Dataset[]
  batches: { id: string; inserted: number; duplicates: number; invalid: number; errors: { row: number; error: string }[] }[]
  templates: Record<string, Template>
  reports: ReportSummary[]
  runs: AnalysisRun[]
}
export interface Metric {
  id: string; name: string; value: string | number | null; previous?: string | null; growth_percent?: string | null
  samples?: number; missing?: number; unit: string; definition: string; visibility: string; trend?: Record<string, string | null>
}
export interface Finding {
  view: string; title: string; dimension: string; text: string; scope: string; counter: string; unknowns: string
  evidence_ids: string[]; visibility: string
}
export interface AnalysisReport extends ReportSummary {
  current: boolean
  scope_topic: string
  sources?: { counts: Record<string, number>; previous: Record<string, number>; categories: Record<string, number>; keywords: Record<string, number>; platforms: Record<string, number>; trend: Record<string, number> }
  metrics?: Metric[]
  operational_metrics?: Metric[]
  findings?: Finding[]
  evidence: { id: string; title?: string; url?: string; summary?: string; name?: string; value?: string; definition?: string }[]
  pending?: number
  model_calls: number
}
export type AnalysisApi = <T>(path: string, body?: unknown) => Promise<T>
