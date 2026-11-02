import { Navigate, useLocation } from 'react-router'

const legacy: Record<string, [string, string]> = {
  rules: ['/cron', 'plan'],
  content: ['/content', 'drafts'],
  tasks: ['/cron', 'history'],
  sources: ['/materials', 'sources'],
  organized: ['/materials', 'organized'],
  topics: ['/content', 'topics'],
  reports: ['/overview', 'reports']
}

export function LegacyPage({ to }: { to?: string }) {
  const location = useLocation()
  const query = new URLSearchParams(location.search)
  const [path, tab] = to ? to.split('?tab=') : legacy[query.get('section') || 'rules'] || legacy.rules
  query.delete('section')

  if (tab) {
    query.set('tab', tab)
  }

  return <Navigate replace to={`${path}?${query}`} />
}
