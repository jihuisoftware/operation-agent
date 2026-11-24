import { Button, Codicon, Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, type PluginContext } from '@hermes/plugin-sdk'
import type { JSONContent } from '@tiptap/core'
import { lazy, Suspense, useEffect, useState } from 'react'

import { AssetImage } from './asset-image'
import { ContentPreview } from './content-preview'
import { versionRequest } from './content-version-actions'
import type { RecordRow } from './types'
import { projection } from './writing/projection'

const DocumentEditor = lazy(() => import('./writing/editor').then(module => ({ default: module.DocumentEditor })))

interface Manuscript extends RecordRow {
  title: string
  body: string
  asset_ids: string[]
  editor_document?: JSONContent
  release?: { revision?: number; state: string }
}

function isEdited(row: Manuscript, title: string, body: string, document?: JSONContent) {
  return title !== row.title || body !== row.body || document !== row.editor_document
}

interface Props {
  ctx: PluginContext
  id: string
  initialReview: boolean
  close: () => void
  refresh: () => Promise<unknown>
  returnFocus: () => void
}

export function ContentEditDialog({ ctx, id, initialReview, close, refresh, returnFocus }: Props) {
  const [review, setReview] = useState(initialReview)
  const [row, setRow] = useState<Manuscript | null>(null)
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [document, setDocument] = useState<JSONContent>()
  const [busy, setBusy] = useState(false)
  const [discard, setDiscard] = useState(false)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    if (review) { return }
    let live = true
    setRow(null)
    setError('')
    void ctx.rest<{ content: Manuscript }>(`/content/${encodeURIComponent(id)}/details`).then(({ content }) => {
      if (!live) { return }
      setTitle(content.title)
      setBody(content.body)
      setDocument(content.editor_document)
      setRow(content)
    }).catch(reason => { if (live) { setError(String(reason)) } })

    return () => { live = false }
  }, [ctx, id, review, retry])

  const dirty = !review && row && isEdited(row, title, body, document)
  const projected = document ? projection(document) : null
  const text = projected?.body ?? body

  const requestClose = () => {
    if (busy) { return }

    if (dirty) { setDiscard(true) } else { close() }
  }

  const save = async () => {
    if (!row || busy || !dirty) { return }
    setBusy(true)
    setError('')

    try {
      await ctx.rest(`/content/${encodeURIComponent(id)}/versions`, { method: 'POST', body: versionRequest(row, {
        title, ...(document ? { editor_document: document } : { body }), expected_release_revision: row.release?.revision ?? 0
      }) })
      await refresh()
      close()
    } catch (reason) { setError(String(reason)) }
    finally { setBusy(false) }
  }

  return <Dialog onOpenChange={open => { if (!open) { requestClose() } }} open>
    <DialogContent bodyClassName="flex max-h-[86vh] flex-col gap-0 overflow-hidden p-0" className="w-[94vw] max-w-4xl" onCloseAutoFocus={event => { event.preventDefault(); returnFocus() }}>
      <DialogHeader className="shrink-0 border-b px-6 py-4">
        <DialogTitle>编辑稿件</DialogTitle>
        <DialogDescription className="sr-only">编辑标题、正文，或查看封面与审核排期。</DialogDescription>
      </DialogHeader>
      <div className="flex shrink-0 gap-1 border-b px-6 py-2">
        <Button aria-pressed={!review} disabled={busy} onClick={() => setReview(false)} size="sm" variant={review ? 'ghost' : 'secondary'}>稿件内容</Button>
        <Button aria-pressed={review} disabled={busy || Boolean(dirty)} onClick={() => setReview(true)} size="sm" variant={review ? 'secondary' : 'ghost'}>封面与审核</Button>
      </div>
      <div className="min-h-0 overflow-y-auto">
        {review ? <div className="p-6"><ContentPreview ctx={ctx} embedded identity={id} publication={false} refresh={refresh} /></div> :
          row ? <div className="grid gap-6 p-6 sm:grid-cols-[8rem_minmax(0,1fr)]">
            <aside className="space-y-2"><div className="text-xs font-medium text-muted-foreground">稿件封面</div>
              {row.asset_ids?.[0] ? <AssetImage className="aspect-[3/4] w-28 rounded-lg border object-contain sm:w-full" ctx={ctx} id={row.asset_ids[0]} /> :
                <div className="flex aspect-[3/4] w-28 flex-col items-center justify-center gap-2 rounded-lg border border-dashed bg-muted/30 text-xs text-muted-foreground sm:w-full"><Codicon name="file-media" />暂无封面</div>}
            </aside>
            <div className="min-w-0 space-y-5">
              <label className="grid gap-2 text-xs font-medium text-muted-foreground">标题
                <input className="w-full border-b bg-transparent pb-2 text-xl font-semibold leading-snug text-foreground focus-visible:outline-primary" disabled={busy} onChange={event => setTitle(event.target.value)} value={title} />
              </label>
              <div className="space-y-2"><div className="flex justify-between text-xs text-muted-foreground"><span>正文</span><span>{Array.from(text).length} 字</span></div>
                {document ? <div className="overflow-hidden rounded-lg border [&_.writing-document]:min-h-52 [&_.writing-document]:p-4"><Suspense fallback={<p>正在载入编辑器…</p>}>
                  <DocumentEditor ctx={ctx} disabled={busy} document={document} onChange={setDocument} session={id} />
                </Suspense></div> : <textarea aria-label="正文" className="min-h-56 w-full resize-y rounded-lg border bg-background px-4 py-3 text-sm leading-7 focus-visible:outline-primary" disabled={busy} onChange={event => setBody(event.target.value)} value={body} />}
              </div>
            </div>
          </div> : !error && <p className="p-6" role="status">正在读取稿件…</p>}
        {error && <p className="px-6 py-3 text-destructive" role="alert">{error} {!row && <Button onClick={() => setRetry(n => n + 1)} variant="link">重试</Button>}</p>}
      </div>
      {!review && <EditorFooter busy={busy} canSave={Boolean(dirty && title.trim() && text.trim() && !projected?.pending_images.length)}
        close={close} dirty={Boolean(dirty)} discard={discard} requestClose={requestClose} resume={() => setDiscard(false)} save={save} />}
    </DialogContent>
  </Dialog>
}


interface FooterProps {
  busy: boolean
  dirty: boolean
  discard: boolean
  canSave: boolean
  close: () => void
  resume: () => void
  requestClose: () => void
  save: () => Promise<void>
}

function EditorFooter({ busy, dirty, discard, canSave, close, resume, requestClose, save }: FooterProps) {
  return <footer className="flex shrink-0 flex-wrap items-center justify-end gap-2 border-t bg-muted/20 px-6 py-3">
        {discard ? <>
          <span className="mr-auto text-sm">放弃未保存的修改？</span>
          <Button onClick={resume} variant="outline">继续编辑</Button>
          <Button onClick={close} variant="destructive">放弃修改</Button>
        </> : <>
          {dirty && <span className="mr-auto text-xs text-muted-foreground">保存后请重新审核稿件</span>}
          <Button disabled={busy} onClick={requestClose} variant="outline">关闭</Button>
          <Button disabled={busy || !canSave} onClick={() => void save()}>{busy ? '正在保存…' : '保存修改'}</Button>
        </>}
      </footer>
}
