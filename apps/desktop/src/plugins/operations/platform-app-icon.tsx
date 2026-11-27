import { SiBilibili, SiTiktok, SiWechat, SiXiaohongshu, SiZhihu } from '@icons-pack/react-simple-icons'

interface AppIcon {
  Icon: typeof SiZhihu
  tile: string
  glyph: string
}

const platformIcons: Partial<Record<string, AppIcon>> = {
  xiaohongshu: { Icon: SiXiaohongshu, tile: 'bg-[#ff2442]', glyph: 'size-10/12 text-white' },
  zhihu: { Icon: SiZhihu, tile: 'bg-white', glyph: 'size-full text-[#0084ff]' },
  bilibili: { Icon: SiBilibili, tile: 'bg-[#fb7299]', glyph: 'size-9/12 text-white' },
  wechat: { Icon: SiWechat, tile: 'bg-[#07c160]', glyph: 'size-9/12 text-white' },
  douyin: { Icon: SiTiktok, tile: 'bg-[#161823]', glyph: 'size-8/12 text-white drop-shadow-[-1px_-1px_0_#25f4ee] drop-shadow-[1px_1px_0_#fe2c55]' }
}

interface PlatformAppIconProps {
  platform: string
  compact?: boolean
}

export function PlatformAppIcon({ platform, compact = false }: PlatformAppIconProps) {
  const icon = platformIcons[platform]

  if (!icon) { return null }

  return (
    <span
      aria-hidden="true"
      className={`inline-flex shrink-0 items-center justify-center overflow-hidden ${compact ? 'size-5 rounded-[5px]' : 'size-7 rounded-[7px]'} ${icon.tile}`}
    >
      <icon.Icon className={icon.glyph} />
    </span>
  )
}
