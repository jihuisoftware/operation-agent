import { Button, Codicon, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { lazy, Suspense } from 'react'
import { Navigate, useLocation, useSearchParams } from 'react-router'

import { useOwnerContext } from './use-owner-context'

const MessagePage = lazy(() => import('./message-page').then(m => ({ default: m.MessagePage })))
const WritingList = lazy(() => import('./writing/list').then(m => ({ default: m.WritingList })))
const SourceLibrary = lazy(() => import('./source-library').then(m => ({ default: m.SourceLibrary })))
const OrganizedLibrary = lazy(() => import('./organized-library').then(m => ({ default: m.OrganizedLibrary })))
const TopicsPanel = lazy(() => import('./topics-panel').then(m => ({ default: m.TopicsPanel })))
const AnalysisPage = lazy(() => import('./analysis-page').then(m => ({ default: m.AnalysisPage })))
const LibraryPage = lazy(() => import('./library-page').then(m => ({ default: m.LibraryPage })))
const ContentLibrary = lazy(() => import('./content-library').then(m => ({ default: m.ContentLibrary })))
const BusinessPage = lazy(() => import('./business-page').then(m => ({ default: m.BusinessPage })))
export const sections = {
  materials: {
    title: '资料',
    icon: 'library',
    tabs: [
      ['sources', '采集来源'],
      ['organized', '整理分类'],
      ['assets', '图片素材'],
      ['business', '业务数据']
    ]
  },
  analysis: {
    title: '分析',
    icon: 'graph',
    tabs: [
      ['analytics', '数据分析'],
      ['industry', '行业分析']
    ]
  },
  content: {
    title: '内容',
    icon: 'file-media',
    tabs: [
      ['drafts', '待审核'],
      ['needs_work', '待完善'],
      ['pending', '已排期'],
      ['published', '发布记录'],
      ['topics', '选题'],
      ['writing', '写作草稿'],
    ]
  },
  interactions: {
    title: '互动',
    icon: 'comment-discussion',
    tabs: [
      ['messages', '消息处理'],
      ['comment', '主动评论']
    ]
  }
}
export type Section = keyof typeof sections

interface SectionProps { ctx: PluginContext; section: Section }

export function SectionPage(props: SectionProps) {
  const [params] = useSearchParams()
  const location = useLocation()
  const old = params.get('tab') || ''
  if (props.section === 'interactions' && ['reply', 'dm', 'inbox', 'follow'].includes(old)) {
    const next = new URLSearchParams(params)
    next.set('tab', 'messages')
    const record = params.get('record') || params.get('action') || params.get('selected')
    if (record) next.set('record', record)
    next.set(old === 'inbox' ? 'state' : 'source', old === 'inbox' ? 'attention' : old)
    return <Navigate replace to={location.pathname + '?' + next} />
  }
  if (props.section === 'interactions' && old === 'unverified') {
    const next = new URLSearchParams(params)
    next.set('tab', 'history')
    next.set('historyView', 'operations.unverified')
    if (!next.has('record') && next.has('action')) next.set('record', next.get('action')!)
    return <Navigate replace to={'/cron?' + next} />
  }
  return <SectionContent {...props} />
}

function SectionContent({ ctx, section }: SectionProps) {
  const owner = useValue(host.state.requestOwner)

  const bound = useOwnerContext(ctx, owner)

  const [params, setParams] = useSearchParams()
  const config = sections[section]
  const tab = config.tabs.some(([key]) => params.get('tab') === key) ? params.get('tab')! : config.tabs[0][0]

  return (
    <main className="flex h-full min-w-0 flex-col" key={JSON.stringify(owner)}>
      <header className="flex flex-wrap items-center gap-2 p-4">
        <Codicon name={config.icon} />
        <h1 className="mr-auto text-xl font-semibold">{config.title}</h1>
        {section === 'content' && (
          <Button onClick={() => host.navigate('/artifacts')} variant="ghost">
            成果文件
          </Button>
        )}
      </header>
      <nav aria-label={`${config.title}分类`} className="flex flex-wrap gap-2 px-4 pb-3">
        {config.tabs.map(([key, label]) => (
          <Button
            aria-pressed={tab === key}
            key={key}
            onClick={() =>
              setParams(previous => {
                const next = new URLSearchParams(previous)
                next.set('tab', key)

                for (const field of ['record', 'selected', 'action', 'before', 'source', 'state']) { next.delete(field) }

                return next
              })
            }
            size="sm"
            variant={tab === key ? 'secondary' : 'ghost'}
          >
            {label}
          </Button>
        ))}
      </nav>
      <div className="min-h-0 flex-1 overflow-auto">
        <Suspense
          fallback={
            <p className="p-4" role="status">
              正在加载…
            </p>
          }
        >
          {section === 'analysis' ? (
            <AnalysisPage
              ctx={bound}
              initialReport={params.get('record') || ''}
              key={params.toString()}
              stage={tab as 'analytics' | 'industry'}
            />
          ) : tab === 'messages' ? <MessagePage ctx={bound} /> : tab === 'sources' ? (
            <SourceLibrary
              ctx={bound}
              initialQuery={params.get('q') || ''}
              initialSelected={params.get('record')}
              key={params.toString()}
            />
          ) : tab === 'organized' ? (
            <OrganizedLibrary
              ctx={bound}
              initialCategory={params.get('category') || ''}
              initialQuery={params.get('q') || ''}
              key={params.toString()}
            />
          ) : tab === 'topics' ? (
            <TopicsPanel ctx={bound} />
          ) : tab === 'writing' ? (<WritingList ctx={bound} />) : section === 'content' ? (
            <ContentLibrary ctx={bound} key={params.toString()} record={params.get('record') || ''} tab={tab} />
          ) : tab === 'business' ? (
            <BusinessPage ctx={bound} />
          ) : (
            <LibraryPage
              ctx={bound}
              filter={section === 'materials' ? '' : tab}
              key={params.toString()}
              record={params.get('record') || ''}
              section={section === 'materials' ? 'assets' : section}
            />
          )}
        </Suspense>
      </div>
    </main>
  )
}
