import { Extension } from '@tiptap/core'
import { Fragment, Slice } from '@tiptap/pm/model'
import { NodeSelection, Plugin, PluginKey } from '@tiptap/pm/state'
import { dropPoint } from '@tiptap/pm/transform'

const dragging = new PluginKey<number | null>('writing-image-drag')
export const ImageDrag = Extension.create({
  name: 'writingImageDrag',
  addProseMirrorPlugins() {
    return [
      new Plugin<number | null>({
        key: dragging,
        state: {
          init: () => null,
          apply: (transaction, previous) => {
            const explicit = transaction.getMeta(dragging)

            if (explicit !== undefined) {
              return explicit
            }

            if (previous === null) {
              return null
            }

            const mapped = transaction.mapping.mapResult(previous)

            return mapped.deleted || transaction.doc.nodeAt(mapped.pos)?.type.name !== 'image' ? null : mapped.pos
          }
        },
        props: {
          handleDOMEvents: {
            dragstart(view, event) {
              const target = event.target as HTMLElement

              const handle =
                target.closest('[data-writing-image]') ||
                target.closest('.node-image')?.querySelector('[data-writing-image]')

              if (!handle || !event.dataTransfer) {
                return false
              }

              const position = view.posAtDOM(handle, 0),
                node = view.state.doc.nodeAt(position)

              if (node?.type.name !== 'image') {
                return false
              }

              view.dispatch(
                view.state.tr.setSelection(NodeSelection.create(view.state.doc, position)).setMeta(dragging, position)
              )
              // A closed slice avoids the table context ProseMirror adds to clipboard HTML.
              view.dragging = { slice: new Slice(Fragment.from(node), 0, 0), move: true }
              event.dataTransfer.clearData()
              event.dataTransfer.setData('text/plain', node.attrs.alt || '图片')
              event.dataTransfer.effectAllowed = 'move'

              return true
            },
            dragend(view) {
              view.dispatch(view.state.tr.setMeta(dragging, null))

              return false
            }
          },
          handleDrop(view, event) {
            const from = dragging.getState(view.state)

            if (from === null || from === undefined) {
              return false
            }

            const node = view.state.doc.nodeAt(from),
              point = view.posAtCoords({ left: event.clientX, top: event.clientY })

            if (!node || !point) {
              return true
            }

            const transaction = view.state.tr.delete(from, from + node.nodeSize)

            const position = dropPoint(
              transaction.doc,
              transaction.mapping.map(point.pos),
              new Slice(Fragment.from(node), 0, 0)
            )

            if (position === null) {
              return true
            }

            transaction.insert(position, node).setMeta(dragging, null)
            transaction.setSelection(NodeSelection.create(transaction.doc, position))
            view.dispatch(transaction.scrollIntoView())

            return true
          }
        }
      })
    ]
  }
})
