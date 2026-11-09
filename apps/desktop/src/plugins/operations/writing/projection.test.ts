import { expect, it } from 'vitest'

import fixture from './fixtures/document.json'
import { projection } from './projection'
it('matches the shared publication text, Unicode count and cover-first gallery contract', () => {
  expect(projection(fixture.document, fixture.cover)).toEqual(fixture.expected)
})
