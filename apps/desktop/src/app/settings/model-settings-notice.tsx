import { Button } from '@/components/ui/button'
import { Loader2 } from '@/lib/icons'

interface Props {
  error: string
  skewRestart: boolean
  restarting: boolean
  onRestart: () => Promise<void>
  copy: { restartingBackend: string; restartBackend: string }
}

export function ModelSettingsNotice({ error, skewRestart, restarting, onRestart, copy }: Props) {
  if (!error) {
    return null
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-destructive">
      <span>{error}</span>
      {skewRestart && (
        <Button disabled={restarting} onClick={() => void onRestart()} size="sm" variant="textStrong">
          {restarting && <Loader2 className="size-3.5 animate-spin" />}
          {restarting ? copy.restartingBackend : copy.restartBackend}
        </Button>
      )}
    </div>
  )
}
