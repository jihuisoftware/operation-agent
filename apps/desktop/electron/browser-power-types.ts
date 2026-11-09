export interface BrowserPowerOwner {
  connectionId: string | null
  profile: string | null
  account_id: string
}

export interface BrowserPowerEntry extends BrowserPowerOwner {
  command_id: string
  worker: string
  business_id: string
  topic_id: string
  expires: number
  guest_id: number
  epoch: string
  phase: 'not_started' | 'read_only' | 'submission_started'
  interrupted?: boolean
  sleep_started_at?: number
  resumed_at?: number
  reason?: 'SYSTEM_SUSPENDED' | 'BROWSER_UNAVAILABLE'
}

export interface BrowserPowerState {
  epoch: string
  suspended: boolean
  slept: boolean
  recovery_error?: string
  entries: BrowserPowerEntry[]
}

export interface BrowserPowerApi {
  state(owner: BrowserPowerOwner): Promise<BrowserPowerState>
  begin(entry: Omit<BrowserPowerEntry, 'epoch' | 'phase'>, epoch: string): Promise<BrowserPowerEntry>
  phase(command: string, epoch: string, phase: BrowserPowerEntry['phase']): Promise<void>
  finish(command: string, epoch: string, acknowledged?: boolean): Promise<void>
  acknowledged(owner: BrowserPowerOwner, command: string): Promise<void>
  onChange(callback: (state: Omit<BrowserPowerState, 'entries'>) => void): () => void
}
