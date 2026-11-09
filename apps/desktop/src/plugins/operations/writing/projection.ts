import type { JSONContent } from '@tiptap/core'

function inline(nodes: JSONContent[]) {
  let buffer = '',
    current = ''

  const parts: string[] = []

  const flush = () => {
    parts.push(buffer + (current && buffer !== current ? `（${current}）` : ''))
    buffer = ''
  }

  for (const node of nodes) {
    const href = String(node.marks?.find(mark => mark.type === 'link')?.attrs?.href || '')

    if (href !== current || node.type === 'hardBreak') {
      flush()
      current = href
    }

    if (node.type === 'hardBreak') {
      parts.push('\n')
    } else {
      buffer += node.text || ''
    }
  }

  flush()

  return parts.join('')
}

export function projection(document: JSONContent, cover = '') {
  const assets: string[] = [],
    pending: string[] = []

  const block = (node: JSONContent): string => {
    const children = node.content || [],
      attrs = node.attrs || {},
      kind = node.type

    if (['paragraph', 'heading', 'codeBlock'].includes(kind || '')) {
      return inline(children)
    }

    if (kind === 'image') {
      if (attrs.assetId) {
        assets.push(attrs.assetId)
      } else {
        pending.push('未导入图片')
      }

      return ''
    }

    if (kind === 'uploadPlaceholder') {
      pending.push(attrs.name || '未上传图片')

      return ''
    }

    if (kind === 'bulletList' || kind === 'orderedList') {
      return children
        .map((child, index) => {
          const prefix = kind === 'orderedList' ? `${(attrs.start || 1) + index}. ` : '• '

          return (
            prefix +
            block(child)
              .split('\n')
              .join('\n' + ' '.repeat(prefix.length))
          )
        })
        .join('\n')
    }

    if (kind === 'table') {
      return children.map(block).join('\n')
    }

    if (kind === 'tableRow') {
      return children.map(child => block(child).replaceAll('\n', ' / ')).join(' | ')
    }

    if (kind === 'horizontalRule') {
      return '——'
    }

    return children
      .map(block)
      .filter(Boolean)
      .join(['listItem', 'tableCell', 'tableHeader'].includes(kind || '') ? '\n' : '\n\n')
  }

  const body = block(document)

  return {
    body,
    body_characters: Array.from(body).length,
    asset_ids: [...new Set([...(cover ? [cover] : []), ...assets])],
    pending_images: pending
  }
}
