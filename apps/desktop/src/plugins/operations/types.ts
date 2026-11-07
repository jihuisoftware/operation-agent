export interface Policy {
  business_theme?: string
  business_subtype?: string
  schema_version: number
  modules: Record<string, boolean>
  enabled: boolean
  paused: boolean
  topic: string
  audience: string
  goal: string
  style: string
  brand: string
  account_id: string
  timezone: string
  sources: string[]
  rss_sources: string[]
  keywords: string[]
  knowledge: string[]
  follow_terms: string[]
  allowed: Record<string, boolean>
  limits: Record<string, number>
  times: Record<string, string[]>
  deadline: string
  priority: number
  model_calls: number
  model_budget_mode?: 'calls' | 'tokens'
  model_tokens?: number
}

export interface RecordRow {
  id: string
  [key: string]: unknown
}
export interface OperationsState {
  execution_block?: { error_code: string; error: string; cause_at?: number } | null
  web_held?: boolean
  version: number
  policy: Policy
  online: boolean
  runs: RecordRow[]
  actions: RecordRow[]
  events: RecordRow[]
  source: RecordRow[]
  asset: RecordRow[]
  content: RecordRow[]
  metric: RecordRow[]
  report: RecordRow[]
  task: RecordRow[]
  inbox: RecordRow[]
  brief: RecordRow[]
  block: RecordRow[]
}

export interface BrowserCommand {
  id: string
  kind: 'account' | 'inbox' | 'publish' | 'interact' | 'verify'
  payload: Record<string, any>
  expires: number
}

export interface Guest extends HTMLElement {
  getWebContentsId?: () => number
  capturePage?: () => Promise<{ resize: (options: { width: number }) => { toDataURL: () => string } }>
  executeJavaScript: (code: string) => Promise<any>
  loadURL: (url: string) => Promise<void>
  isLoadingMainFrame?: () => boolean
  getURL: () => string
}

export type Api = <T>(path: string, body?: unknown, method?: string) => Promise<T>
