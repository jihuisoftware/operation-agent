/** Fast pages continue immediately; these are ceilings for slow proxy connections. */
export const PAGE_LOAD_MS = 120_000
export const SCRIPT_MS = 10_000
export const BACKEND_MS = 30_000
export const READINESS_MS = 90_000
export const LOGIN_MS = 45_000

export function workerRequestTimeout(path: string) {
  if (path === '/worker/publish-decision') { return 360_000 }

  return path === '/worker/verify-images' ? 60_000 : BACKEND_MS
}
