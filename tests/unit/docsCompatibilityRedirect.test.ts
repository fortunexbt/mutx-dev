import { GET, HEAD } from '../../app/docs/contracts/api/webhooks/route'

describe('legacy webhook documentation route', () => {
  it.each([GET, HEAD])('permanently redirects to the canonical reference', (handler) => {
    const response = handler()

    expect(response.status).toBe(308)
    expect(response.headers.get('location')).toBe('/docs/reference/webhooks')
  })
})
