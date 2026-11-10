import { Navigate, useParams } from 'react-router-dom'

import { ResourcePage } from './ResourcePage'
import { RESOURCES, type ResourceDef } from './schema'

const PAGES: ResourceDef['key'][] = ['courses', 'events', 'achievements', 'news', 'team', 'testimonials']

/** /marketing/site/:resource — courses, events, achievements, news, team, testimonials. */
export function SiteResourceRoute() {
  const { resource = '' } = useParams()
  if (!PAGES.includes(resource as ResourceDef['key']) || !(resource in RESOURCES)) return <Navigate to="/marketing/site" replace />
  return <ResourcePage key={resource} resource={resource as ResourceDef['key']} />
}
