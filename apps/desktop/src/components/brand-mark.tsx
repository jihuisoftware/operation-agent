import { cn } from '@/lib/utils'
import { useTheme } from '@/themes'

const assetPath = (path: string) => `${import.meta.env.BASE_URL}${path.replace(/^\/+/, '')}`

// The operations mark shares the generated application artwork and native
// transparent corners. Legacy asset filenames remain stable for cached clients.
export function BrandMark({ className, ...props }: React.ComponentProps<'span'>) {
  const { renderedMode } = useTheme()
  const dark = renderedMode === 'dark'

  return (
    <span className={cn('inline-flex size-14 shrink-0 items-center justify-center', className)} {...props}>
      <img alt="" className="size-full object-contain" src={assetPath(dark ? 'nous-girl-dark.png' : 'nous-girl.png')} />
    </span>
  )
}
