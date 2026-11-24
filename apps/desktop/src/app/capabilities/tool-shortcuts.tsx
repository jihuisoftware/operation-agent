import { Button } from '@/components/ui/button'
import { Codicon } from '@/components/ui/codicon'

import { toggleTerminalPane } from '../right-sidebar/terminal/reveal-focus'

interface ToolShortcutsProps {
  onManagePlugins?: () => void
}

export function ToolShortcuts({ onManagePlugins }: ToolShortcutsProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 px-4 py-2">
      {onManagePlugins && (
        <Button onClick={onManagePlugins} size="sm" variant="outline">
          <Codicon name="extensions" />
          管理插件
        </Button>
      )}
      <Button onClick={toggleTerminalPane} size="sm" variant="ghost">
        <Codicon name="terminal" />
        终端
      </Button>
    </div>
  )
}
