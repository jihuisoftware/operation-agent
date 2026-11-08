import { Button, Codicon, host, type PluginContext, useValue } from '@hermes/plugin-sdk'
import { lazy, Suspense, useMemo } from 'react'
import { useSearchParams } from 'react-router'

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
      ['writing', '写作草稿'],
      ['pending', '已排期'],
      ['published', '发布记录'],
      ['topics', '选题']
    ]
  },
  interactions: {
    title: '互动',
    icon: 'comment-discussion',
    tabs: [
      ['reply', '评论回复'],
      ['comment', '主动评论'],
      ['dm', '收到私信'],
      ['follow', '回关']
    ]
  }
}
export type Section = keyof typeof sections

export function SectionPage({ ctx, section }: { ctx: PluginContext; section: Section }) {
  const owner = useValue(host.state.requestOwner)

  const bound = useMemo<PluginContext>(
    () => ({ ...ctx, rest: (path, options) => ctx.rest(path, { ...options, owner }) }),
    [ctx, owner]
  )

  const [params, setParams] = useSearchParams()
  const config = sections[section]
  const tab = config.tabs.some(([key]) => params.get('tab') === key) ? params.get('tab')! : config.tabs[0][0]

  return (
    <main className="flex h-full min-w-0 flex-col" key={JSON.stringify(owner)}>
      <header className="flex flex-wrap items-center gap-2 p-4">
        <Codicon name={config.icon} />
        <h1 className="mr-auto text-xl font-semibold">{config.title}</h1>
        <Button onClick={() => host.navigate('/cron?tab=plan')} variant="ghost">
          调整运营设置
        </Button>
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

                for (const field of ['record', 'selected', 'action', 'before']) { next.delete(field) }

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
          ) : tab === 'sources' ? (
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
