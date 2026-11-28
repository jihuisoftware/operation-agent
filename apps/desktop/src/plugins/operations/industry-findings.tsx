import { Badge, Button } from '@hermes/plugin-sdk'
import { useRef, useState } from 'react'

import type { AnalysisReport, Finding } from './analysis-types'

const PAGE_SIZE = 16

interface IndustryFindingsProps {
  findings: Finding[]
  evidenceItems: AnalysisReport['evidence']
  onSource: (id: string) => void
}

export function IndustryFindings({ findings, evidenceItems, onSource }: IndustryFindingsProps) {
  const [page, setPage] = useState(1)
  const list = useRef<HTMLDivElement>(null)
  const offset = (page - 1) * PAGE_SIZE
  const visible = findings.slice(offset, offset + PAGE_SIZE)

  function changePage(next: number) {
    setPage(next)
    list.current?.scrollIntoView({ block: 'start' })
  }

  return (
    <div className="space-y-5" ref={list}>
      {!findings.length && <p className="bg-muted/30 p-4">当前视角证据不足，尚未形成可用结论。</p>}
      {visible.map((finding, index) => <article className="space-y-3 border-b pb-4" key={offset + index}>
        <div className="flex gap-2"><Badge>{finding.dimension}</Badge><Badge>{finding.visibility === 'public' ? '可公开' : '内部经营参考'}</Badge></div><h3 className="font-medium">{finding.title}</h3><p>{finding.text}</p>
        <details>
          <summary className="cursor-pointer">依据、适用范围与待核实事项</summary>
          <div className="mt-3 space-y-2 text-xs">
            <p>适用范围：{finding.scope}</p>
            <p>反向证据：{finding.counter}</p>
            <p>待核实：{finding.unknowns}</p>
          </div>
          <ul className="mt-4 space-y-5">
            {finding.evidence_ids.map(id => {
              const evidence = evidenceItems.find(item => item.id === id)
              const title = evidence?.title || evidence?.name || id
              const summary = evidence?.summary || evidence?.definition
              return (
                <li className="space-y-2 text-sm" key={id}>
                  <p className="font-semibold">{title === evidence?.url ? '未命名来源' : title}</p>
                  {summary && <p>{summary}</p>}
                  {evidence?.value != null && <p>{evidence.value}</p>}
                  {evidence?.url && (
                    <Button onClick={() => onSource(id)} size="sm" variant="outline">查看原始图文</Button>
                  )}
                </li>
              )
            })}
          </ul>
        </details>
      </article>)}
      {['趋势', '需求', '竞争', '产品价格', '机会', '风险'].filter(d => !findings.some(f => f.dimension === d)).map(d => <p className="text-xs text-muted-foreground" key={d}>{d}：证据不足</p>)}
      <nav aria-label="分析结论分页" className="flex items-center gap-3">
        <Button disabled={page === 1} onClick={() => changePage(page - 1)} variant="outline">上一页</Button>
        <span aria-live="polite" className="text-xs text-muted-foreground">共 {findings.length} 条 · 第 {page} 页</span>
        <Button disabled={offset + PAGE_SIZE >= findings.length} onClick={() => changePage(page + 1)} variant="outline">下一页</Button>
      </nav>
    </div>
  )
}
