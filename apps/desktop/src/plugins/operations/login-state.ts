import type { CronBlueprintOwner } from '@hermes/plugin-sdk'
import { atom } from 'nanostores'

export interface LoginObservation {
  state: 'logged_in' | 'logged_out' | 'verification' | 'unknown'
  account_id: string
}
export interface PlatformLogin {
  id: string
  name: string
  url: string
  state: LoginObservation['state'] | 'unchecked' | 'stale' | 'offline' | 'mismatch'
  observed_state: LoginObservation['state'] | null
  checked_at: string | null
  account_id: string
  confirmed_at?: string | null
  account_mismatch?: boolean
  checked_in_current_window?: boolean
  reason: string
}
export interface PlatformLogins {
  platforms: PlatformLogin[]
  worker_online: boolean
}
export interface LoginRequest {
  owner: CronBlueprintOwner
  platform: string
  url: string
  id: string
}
export const $loginWorker = atom<{ owner: CronBlueprintOwner; worker: string } | null>(null)
export const $loginRequest = atom<LoginRequest | null>(null)
export const $loginStatusRevision = atom(0)
export const $loginNavigation = atom<string | null>(null)
export const loginLabels: Record<PlatformLogin['state'], string> = {
  logged_in: '已登录',
  logged_out: '需要登录',
  verification: '需要验证',
  unknown: '无法确认',
  unchecked: '未检查',
  stale: '待复查',
  offline: '窗口离线',
  mismatch: '账号不匹配'
}

export function sameLoginOwner(a: CronBlueprintOwner, b: CronBlueprintOwner) {
  return a.connectionId === b.connectionId && (a.profile || 'default') === (b.profile || 'default')
}
