export interface Totals {
  total_tokens: number
  prompt_tokens: number
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  reasoning_tokens: number
  calls: number
  running: number
  unknown: number
}
export interface Group extends Totals { id: string; label: string }
export interface Summary {
  totals: Totals
  groups: Record<string, Group[]>
  trend: (Totals & { at: string })[]
  since: number
  start: number
  until: number
  period: string
  timezone: string
  partial_history: boolean
}
export interface UsageTask extends Totals {
  id: string; task_name: string; state: string; started: number; ended: number | null
  business_id: string; topic_id: string; run_id: string; stage: string
  business_name: string; topic_name: string; session_id: string; turn_id: string
}
export interface UsageCall {
  id: string; purpose: string; model: string; provider: string; started: number
  received: number | null; state: string; error_type: string
  total_tokens: number | null; prompt_tokens: number | null; output_tokens: number | null
  cache_read_tokens: number | null; cache_write_tokens: number | null; reasoning_tokens: number | null
}
export interface Page<T> { items: T[]; cursor: string | null; until?: number }
