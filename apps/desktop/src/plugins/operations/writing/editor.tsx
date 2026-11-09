import './writing.css'

import type { PluginContext } from '@hermes/plugin-sdk'
import Highlight from '@tiptap/extension-highlight'
import Placeholder from '@tiptap/extension-placeholder'
import { TableKit } from '@tiptap/extension-table'
import TextAlign from '@tiptap/extension-text-align'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { useEffect } from 'react'

import type { Writer } from './controller'
import { ImageDrag } from './image-drag'
import { cleanPaste, mediaNodes, uploadImages } from './media'
import { Toolbar } from './toolbar'

interface Props {
  controller: Writer
  ctx: PluginContext
  disabled: boolean
}

export function WritingEditor({ controller, ctx, disabled }: Props) {
  const editor = useEditor(
    {
      extensions: [
        StarterKit.configure({
          heading: { levels: [1, 2, 3] },
          link: { openOnClick: false, autolink: false, linkOnPaste: false, protocols: ['http', 'https'] }
        }),
        Highlight.configure({ multicolor: true }),
        TableKit,
        TextAlign.configure({ types: ['heading', 'paragraph'] }),
        Placeholder.configure({ placeholder: '从这里开始写作…' }),
        ImageDrag,
        ...mediaNodes(ctx)
      ],
      content: controller.state.get().draft.document,
      onUpdate: ({ editor: current }) => controller.edit({ document: current.getJSON() }),
      editorProps: {
        attributes: { 'aria-label': '正文编辑器', class: 'writing-document' },
        transformPastedHTML: cleanPaste,
        handleDOMEvents: {
          compositionstart: () => {
            controller.composition(true)

            return false
          },
          compositionend: () => {
            controller.composition(false)

            return false
          }
        },
        handlePaste: (_view, event) => {
          const files = Array.from(event.clipboardData?.files || [])

          if (!files.length || !editor) {
            return false
          }

          void uploadImages(editor, ctx, files)

          return true
        },
        handleDrop: (view, event, _slice, moved) => {
          const files = Array.from(event.dataTransfer?.files || [])

          if (moved || !files.length || !editor) {
            return false
          }

          const point = view.posAtCoords({ left: event.clientX, top: event.clientY })

          if (point) {
            editor.commands.setTextSelection(point.pos)
          }

          void uploadImages(editor, ctx, files)

          return true
        }
      }
    },
    [controller, ctx]
  )

  useEffect(() => {
    editor?.setEditable(!disabled)
  }, [editor, disabled])

  useEffect(() => {
    if (!editor) {
      return
    }

    return controller.bindImages(ids => {
      const transaction = editor.state.tr
      const ranges: [number, number][] = []
      editor.state.doc.descendants((node, pos) => {
        if (['image', 'uploadPlaceholder'].includes(node.type.name)) {
          ranges.push([pos, pos + node.nodeSize])
        }
      })

      for (const [from, to] of ranges.reverse()) {
        transaction.delete(from, to)
      }

      transaction.insert(
        transaction.doc.content.size,
        ids.map(assetId => editor.schema.nodes.image.create({ assetId, alt: '图文页面' }))
      )
      editor.view.dispatch(transaction)
    })
  }, [editor, controller])

  return (
    <div className="min-w-0 flex-1">
      {editor && <Toolbar ctx={ctx} editor={editor} />}
      <EditorContent editor={editor} />
    </div>
  )
}
