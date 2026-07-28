jest.mock('framer-motion', () => ({}))
jest.mock('@radix-ui/react-select', () => ({}))
jest.mock('lucide-react', () => ({}))

import {
  getContactSubmissionError,
  resolvePicoContactSubmissionAttempt,
  wasContactSubmissionAccepted,
} from '../../components/pico/PicoContactForm'
import { resolveContactSubmissionAttempt } from '../../components/ContactLeadForm'

describe('Pico contact response handling', () => {
  it('rejects a success-shaped response without durable persistence acknowledgement', () => {
    expect(
      wasContactSubmissionAccepted({
        success: true,
        status: 'accepted',
        persisted: false,
      }),
    ).toBe(false)
  })

  it('accepts the durable persistence acknowledgement without requiring delivery claims', () => {
    expect(
      wasContactSubmissionAccepted({
        success: true,
        status: 'accepted',
        persisted: true,
        notification_scheduled: false,
      }),
    ).toBe(true)
  })

  it('surfaces an actionable API error and falls back for malformed responses', () => {
    expect(
      getContactSubmissionError(
        { error: { message: 'Please email hello@mutx.dev.' } },
        'Please try again.',
      ),
    ).toBe('Please email hello@mutx.dev.')
    expect(getContactSubmissionError(null, 'Please try again.')).toBe('Please try again.')
  })

  it.each([
    ['Pico', resolvePicoContactSubmissionAttempt],
    ['public contact', resolveContactSubmissionAttempt],
  ])('%s form reuses a key for identical retry content and rotates for changed content', (_label, resolve) => {
    const createKey = jest.fn().mockReturnValueOnce('first-key').mockReturnValueOnce('second-key')
    const first = resolve(null, '{"email":"person@example.com"}', createKey)
    const replay = resolve(first, '{"email":"person@example.com"}', createKey)
    const changed = resolve(first, '{"email":"other@example.com"}', createKey)

    expect(replay).toBe(first)
    expect(changed.key).toBe('second-key')
    expect(createKey).toHaveBeenCalledTimes(2)
  })
})
