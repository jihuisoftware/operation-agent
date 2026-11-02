import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, expect, it } from 'vitest'

import { LegacyPage } from './legacy-page'

function Target() {
  const location = useLocation()

  return (
    <p>
      {location.pathname}
      {location.search}
    </p>
  )
}

afterEach(cleanup)
it('redirects old sections while retaining record filters and Profile', async () => {
  render(
    <MemoryRouter initialEntries={['/operations?section=sources&profile=work&record=one&q=keyword']}>
      <Routes>
        <Route element={<LegacyPage />} path="/operations" />
        <Route element={<Target />} path="/materials" />
      </Routes>
    </MemoryRouter>
  )
  expect(await screen.findByText('/materials?profile=work&record=one&q=keyword&tab=sources')).toBeTruthy()
})
