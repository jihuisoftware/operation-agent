import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { saveHermesConfig } from '@/hermes'

import { invalidateHermesConfig, useHermesConfigRecord } from '../hooks/use-config-record'

import { ToggleRow } from './primitives'

interface ParsingSettings {
  enabled: boolean
  parse_images: boolean
  parse_files: boolean
}

function values(raw: unknown): ParsingSettings {
  const value = (raw || {}) as Partial<ParsingSettings>

  return {
    enabled: value.enabled === true,
    parse_images: value.parse_images === true,
    parse_files: value.parse_files === true
  }
}

export function TokenSavingSettings({ profile }: { profile?: string }) {
  const query = useHermesConfigRecord(profile)

  if (!query.data) {
    return <p role="status">{query.error ? '无法读取节省 Token 设置，请稍后重试。' : '正在读取节省 Token 设置…'}</p>
  }

  const scope = query.writeScope ?? profile

  return (
    <ParsingControls
      key={JSON.stringify(scope)}
      onSave={async next => {
        await saveHermesConfig({ token_saving: next }, scope)
        await invalidateHermesConfig(profile)
      }}
      settings={values(query.data.token_saving)}
    />
  )
}

export function ParsingControls({
  settings,
  onSave
}: {
  settings: ParsingSettings
  onSave: (next: ParsingSettings) => Promise<void>
}) {
  const [draft, setDraft] = useState<ParsingSettings | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const current = draft || settings

  const change = (field: keyof ParsingSettings, value: boolean) => {
    setDraft({ ...current, [field]: value })
    setMessage('')
  }

  const save = async () => {
    if (busy || !draft) {
      return
    }

    setBusy(true)

    try {
      await onSave(draft)
      setDraft(null)
      setMessage('已保存，下次新输入及解析调用生效。')
    } catch (error) {
      setMessage(`保存失败：${String(error)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-label="节省 Token 模式" className="my-5 space-y-3">
      <h3 className="font-medium">节省 Token 模式</h3>
      <ToggleRow
        checked={current.enabled}
        description="减少图像与文档进入模型上下文，默认不解析；可单独开启需要的类型。"
        disabled={busy}
        label="启用节省 Token 模式"
        onChange={value => change('enabled', value)}
      />
      <ToggleRow
        checked={!current.enabled || current.parse_images}
        description="识别新附图及通过图像工具读取图片；关闭时不发送图片像素。"
        disabled={busy || !current.enabled}
        label="解析图像"
        onChange={value => change('parse_images', value)}
      />
      <ToggleRow
        checked={!current.enabled || current.parse_files}
        description="展开文件附件引用，以及提取 PDF、Office 等文档正文。PDF 作为图片解析需同时开启两项。"
        disabled={busy || !current.enabled}
        label="解析文件"
        onChange={value => change('parse_files', value)}
      />
      <p className="text-xs text-muted-foreground">
        本地素材上传、预览和业务表格导入继续可用；业务数据发送权限仍单独控制。文字对话、网页正文、普通代码读取及已有上下文仍会消耗
        Token，此模式不是总量硬上限。历史内容不删除；需要减少已有上下文时请新建会话。
      </p>
      <Button disabled={busy || !draft} onClick={() => void save()} size="sm" variant="outline">
        {busy ? '保存中…' : '保存节省设置'}
      </Button>
      {message && (
        <p className="text-xs" role="status">
          {message}
        </p>
      )}
    </section>
  )
}
