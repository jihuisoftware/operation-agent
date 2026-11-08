import { Button, type PluginContext } from '@hermes/plugin-sdk'
import type { Editor } from '@tiptap/core'
import { useEditorState } from '@tiptap/react'
import { useState } from 'react'

import { uploadImages, validLink } from './media'

interface Props { editor: Editor; ctx: PluginContext }

export function Toolbar({ editor, ctx }: Props) {
  useEditorState({ editor, selector: ({ editor: current }) => current.state })

  const [link, setLink] = useState(''),
    [showLink, setShowLink] = useState(false)

  const actions: [string, string, () => void][] = [
    ['加粗', 'bold', () => editor.chain().focus().toggleBold().run()],
    ['斜体', 'italic', () => editor.chain().focus().toggleItalic().run()],
    ['下划线', 'underline', () => editor.chain().focus().toggleUnderline().run()],
    ['高亮', 'highlight', () => editor.chain().focus().toggleHighlight({ color: '#fff3a3' }).run()],
    ['无序列表', 'bulletList', () => editor.chain().focus().toggleBulletList().run()],
    ['有序列表', 'orderedList', () => editor.chain().focus().toggleOrderedList().run()],
    ['引用', 'blockquote', () => editor.chain().focus().toggleBlockquote().run()],
    ['代码块', 'codeBlock', () => editor.chain().focus().toggleCodeBlock().run()]
  ]

  return (
    <div
      aria-label="正文格式"
      className="sticky top-0 z-10 flex flex-wrap gap-1 border-b bg-background p-2"
      role="toolbar"
    >
      <select
        aria-label="标题层级"
        className="bg-background p-1"
        onChange={event => {
          const level = Number(event.target.value) as 1 | 2 | 3

          if (level) {
            editor.chain().focus().setHeading({ level }).run()
          } else {
            editor.chain().focus().setParagraph().run()
          }
        }}
        value={[1, 2, 3].find(level => editor.isActive('heading', { level })) || 0}
      >
        <option value={0}>正文</option>
        {[1, 2, 3].map(n => (
          <option key={n} value={n}>
            标题 {n}
          </option>
        ))}
      </select>
      {actions.map(([title, name, action]) => (
        <Button aria-pressed={editor.isActive(name)} key={name} onClick={action} size="sm" variant="ghost">
          {title}
        </Button>
      ))}
      <Button onClick={() => setShowLink(!showLink)} size="sm" variant="ghost">
        链接
      </Button>
      <Button
        disabled={editor.isActive('table')}
        onClick={() => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()}
        size="sm"
        variant="ghost"
      >
        表格
      </Button>
      {editor.isActive('table') && (
        <>
          <Button onClick={() => editor.chain().focus().addRowAfter().run()} size="sm" variant="ghost">
            加行
          </Button>
          <Button onClick={() => editor.chain().focus().addColumnAfter().run()} size="sm" variant="ghost">
            加列
          </Button>
          <Button onClick={() => editor.chain().focus().deleteTable().run()} size="sm" variant="ghost">
            删除表格
          </Button>
        </>
      )}
      <label className="cursor-pointer p-1 text-sm">
        插图
        <input
          accept="image/png,image/jpeg,image/webp"
          aria-label="上传已授权图片"
          className="sr-only"
          multiple
          onChange={event => {
            void uploadImages(editor, ctx, Array.from(event.target.files || []))
            event.target.value = ''
          }}
          type="file"
        />
      </label>
      <Button
        disabled={!editor.can().undo()}
        onClick={() => editor.chain().focus().undo().run()}
        size="sm"
        variant="ghost"
      >
        撤销
      </Button>
      <Button
        disabled={!editor.can().redo()}
        onClick={() => editor.chain().focus().redo().run()}
        size="sm"
        variant="ghost"
      >
        重做
      </Button>
      {showLink && (
        <div className="flex w-full gap-2">
          <input
            aria-label="链接地址"
            className="flex-1 border bg-background p-2"
            onChange={event => setLink(event.target.value)}
            placeholder="https://"
            value={link}
          />
          <Button
            disabled={!validLink(link)}
            onClick={() => {
              editor.chain().focus().setLink({ href: link }).run()
              setShowLink(false)
            }}
          >
            插入链接
          </Button>
          <Button
            onClick={() => {
              editor.chain().focus().unsetLink().run()
              setShowLink(false)
            }}
          >
            移除链接
          </Button>
        </div>
      )}
    </div>
  )
}
