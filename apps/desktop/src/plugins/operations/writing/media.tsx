import type { PluginContext } from '@hermes/plugin-sdk'
import { type Editor, Node } from '@tiptap/core'
import { NodeViewWrapper, ReactNodeViewRenderer } from '@tiptap/react'

import { AssetImage } from '../asset-image'

export function mediaNodes(ctx: PluginContext) {
  return [
    Node.create({
      name: 'image',
      group: 'block',
      atom: true,
      draggable: true,
      addAttributes: () => ({ assetId: { default: '' }, alt: { default: '' } }),
      parseHTML: () => [
        { tag: 'div[data-asset-id]', getAttrs: element => ({ assetId: element.getAttribute('data-asset-id') }) }
      ],
      renderHTML: ({ node }) => ['div', { 'data-asset-id': node.attrs.assetId }, node.attrs.alt || '图片'],
      addNodeView: () =>
        ReactNodeViewRenderer(({ node }) => (
          <NodeViewWrapper data-drag-handle data-writing-image>
            <AssetImage ctx={ctx} id={node.attrs.assetId} />
          </NodeViewWrapper>
        ))
    }),
    Node.create({
      name: 'uploadPlaceholder',
      group: 'block',
      atom: true,
      selectable: true,
      addAttributes: () => ({ id: { default: '' }, name: { default: '图片待导入' }, state: { default: 'pending' } }),
      parseHTML: () => [
        {
          tag: 'span[data-image-placeholder]',
          getAttrs: element => ({
            name: element.textContent || '外链图片待导入',
            id: crypto.randomUUID(),
            state: 'external'
          })
        }
      ],
      renderHTML: ({ node }) => ['span', { 'data-image-placeholder': 'true' }, node.attrs.name],
      addNodeView: () =>
        ReactNodeViewRenderer(({ node, deleteNode }) => (
          <NodeViewWrapper className="my-3 border border-dashed p-4">
            {node.attrs.name} · 请完成导入或移除{' '}
            <button onClick={deleteNode} type="button">
              移除
            </button>
          </NodeViewWrapper>
        ))
    })
  ]
}

export function validLink(value: string) {
  try {
    const url = new URL(value)

    return value.length <= 2000 && ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password
  } catch {
    return false
  }
}

export function cleanPaste(html: string) {
  // Template contents stay inert: parsing pasted HTML must not fetch external images.
  const template = document.createElement('template')
  template.innerHTML = html
  const doc = template.content
  doc.querySelectorAll('script,style,iframe,object,svg').forEach(node => node.remove())
  doc.querySelectorAll('img').forEach(node => {
    const placeholder = document.createElement('span')
    placeholder.setAttribute('data-image-placeholder', 'true')
    placeholder.textContent = '粘贴图片待导入（请上传本地图片）'
    node.replaceWith(placeholder)
  })
  doc.querySelectorAll('[style]').forEach(node => {
    const element = node as HTMLElement

    if (!['#fff3a3', '#c7e8ff', '#d6f5d6'].includes(element.getAttribute('data-color') || '')) {
      element.style.removeProperty('background-color')
      element.removeAttribute('data-color')
    }
  })
  doc.querySelectorAll('mark').forEach(node => {
    node.removeAttribute('data-color')
    node.removeAttribute('style')
  })
  doc.querySelectorAll('a').forEach(node => {
    if (!validLink(node.getAttribute('href') || '')) {
      node.removeAttribute('href')
    }
  })

  return template.innerHTML
}

function readImage(file: File): Promise<string> {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 20 * 1024 * 1024) {
    return Promise.reject(new Error('请选择 20 MiB 以内的 PNG、JPEG 或 WebP 图片'))
  }

  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1])
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

export async function uploadImages(editor: Editor, ctx: PluginContext, files: File[]) {
  for (const file of files) {
    const id = crypto.randomUUID()
    editor
      .chain()
      .focus()
      .insertContent({ type: 'uploadPlaceholder', attrs: { id, name: `正在上传 ${file.name}`, state: 'pending' } })
      .run()

    try {
      const data = await readImage(file)

      const asset = await ctx.rest<{ id: string }>('/assets', {
        method: 'POST',
        body: { name: file.name, data, authorized: true }
      })

      replacePlaceholder(editor, id, { type: 'image', attrs: { assetId: asset.id, alt: file.name } })
    } catch (reason) {
      replacePlaceholder(editor, id, {
        type: 'uploadPlaceholder',
        attrs: { id, name: `上传失败：${String(reason)}`, state: 'failed' }
      })
    }
  }
}

function replacePlaceholder(editor: Editor, id: string, node: object) {
  if (editor.isDestroyed) {
    return
  }

  editor.state.doc.descendants((child, pos) => {
    if (child.type.name === 'uploadPlaceholder' && child.attrs.id === id) {
      editor.commands.insertContentAt({ from: pos, to: pos + child.nodeSize }, node)

      return false
    }
  })
}
