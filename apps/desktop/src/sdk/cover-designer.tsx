import { createElement, type ReactNode } from 'react'

import { ContribBoundary } from '@/contrib/react/boundary'
import { useContributions } from '@/contrib/react/use-contributions'

export const COVER_DESIGNER_AREA = 'operations.coverDesigner'

export interface CoverJob {
  id: string
  revision: string | number
  state: string
  asset_id?: string
  background?: string
  error?: string
}

export interface CoverRequest {
  request_id: string
  title: string
  subtitle: string
  style: string
  mode: 'upload' | 'background' | 'reuse' | 'ai'
  x: number
  y: number
  previous?: string
  file?: File
  authorized?: boolean
}

export interface CoverDesignerProps {
  title: string
  detail: (id: string) => Promise<CoverJob>
  latest: () => Promise<CoverJob | null>
  start: (request: CoverRequest) => Promise<CoverJob>
  apply: (job: string) => Promise<void>
  image: (id: string) => ReactNode
}

export interface CoverDesignerContribution {
  render: (props: CoverDesignerProps) => ReactNode
}

function Panel({ contribution, props }: { contribution: CoverDesignerContribution; props: CoverDesignerProps }) {
  return createElement(contribution.render, props)
}

export function CoverDesignerPanels({ panel }: { panel: CoverDesignerProps }) {
  const entries = useContributions(COVER_DESIGNER_AREA)

  return <>{entries.map(entry => (
    <ContribBoundary id={entry.id} key={entry.id} variant="pane">
      <Panel contribution={entry.data as CoverDesignerContribution} props={panel} />
    </ContribBoundary>
  ))}</>
}
