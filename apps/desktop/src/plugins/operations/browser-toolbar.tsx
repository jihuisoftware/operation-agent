import { Button, Codicon } from '@hermes/plugin-sdk'

interface Props {
  platformName?: string
  status: string
  loading: boolean
  error: string
  takeOver: () => void
  login: () => void
  hide: () => void
  reopen: () => void
  back: () => void
  release?: () => void
  retryCheck?: () => void
}

export function BrowserToolbar({ status, loading, error, takeOver, login, hide, reopen, back, release, retryCheck, platformName = '小红书' }: Props) {
  return (
    <>
      <header className="shrink-0 border-b border-(--ui-stroke-secondary) bg-(--ui-bg-secondary)">
        <div className="flex items-center justify-between gap-2 px-3 py-2">
          <div className="flex min-w-0 items-center gap-2">
            <Codicon name="browser" />
            <h2 className="truncate text-sm font-semibold">运营画面</h2>
            <span className="text-xs text-muted-foreground">实时网页</span>
          </div>
          <Button aria-label="收起运营画面" onClick={hide} size="icon-sm" variant="ghost">
            <Codicon name="chevron-right" />
          </Button>
        </div>
        <div className="flex flex-wrap gap-2 px-3 pb-2">
          <Button onClick={back} size="sm" variant="outline">
            返回上一页
          </Button>
          <Button onClick={reopen} size="sm" variant="ghost">
            返回首页
          </Button>
          <Button onClick={takeOver} size="sm" variant="outline">
            人工接管网页
          </Button>
          {release && (
            <Button onClick={release} size="sm" variant="outline">
              结束接管
            </Button>
          )}
          <Button onClick={login} size="sm" variant="ghost">
            打开{platformName}／登录
          </Button>
          {retryCheck && <Button onClick={retryCheck} size="sm" variant="ghost">重试账号检查</Button>}
        </div>
        <p className="border-t border-(--ui-stroke-tertiary) px-3 py-2 text-xs text-muted-foreground" role="status">
          {status}
        </p>
      </header>
      {loading && (
        <div className="flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground" role="status">
          <Codicon name="loading" spinning />
          正在加载网页，沿用已保存的登录状态…
        </div>
      )}
      {error && (
        <div className="px-3 py-2 text-sm" role="alert">
          {error}
          <Button onClick={reopen} size="sm" variant="link">
            重新打开网页
          </Button>
        </div>
      )}
    </>
  )
}
