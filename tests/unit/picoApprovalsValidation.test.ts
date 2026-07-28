import {
  approvalCreateSchema,
  approvalResolveSchema,
  validateApprovalRequestId,
} from '../../app/api/pico/approvals/_validation'

describe('pico approvals validation', () => {
  describe('approvalCreateSchema', () => {
    it('accepts a valid approval payload and defaults payload to an empty object', () => {
      const result = approvalCreateSchema.safeParse({
        agent_id: 'agent_123',
        session_id: 'session_456',
        action_type: 'approve_command',
        reviewer_id: '00000000-0000-4000-8000-000000000002',
      })

      expect(result.success).toBe(true)
      if (result.success) {
        expect(result.data.payload).toEqual({})
      }
    })

    it('rejects blank required fields after trimming', () => {
      const result = approvalCreateSchema.safeParse({
        agent_id: '   ',
        session_id: 'session_456',
        action_type: 'approve_command',
        reviewer_id: '00000000-0000-4000-8000-000000000002',
      })

      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues[0]?.message).toBe('agent_id is required')
      }
    })

    it('rejects unexpected fields because the schema is strict', () => {
      const result = approvalCreateSchema.safeParse({
        agent_id: 'agent_123',
        session_id: 'session_456',
        action_type: 'approve_command',
        reviewer_id: '00000000-0000-4000-8000-000000000002',
        payload: {},
        extra: true,
      })

      expect(result.success).toBe(false)
    })

    it('requires an explicit eligible reviewer assignment', () => {
      const result = approvalCreateSchema.safeParse({
        agent_id: 'agent_123',
        session_id: 'session_456',
        action_type: 'approve_command',
      })

      expect(result.success).toBe(false)
    })
  })

  describe('approvalResolveSchema', () => {
    it('accepts a nullable comment', () => {
      const result = approvalResolveSchema.safeParse({ comment: null })

      expect(result.success).toBe(true)
    })

    it('rejects comments longer than 1000 characters', () => {
      const result = approvalResolveSchema.safeParse({ comment: 'x'.repeat(1001) })

      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.error.issues[0]?.message).toBe('comment is too long')
      }
    })
  })

  describe('validateApprovalRequestId', () => {
    it('returns the trimmed request id for valid values', () => {
      expect(validateApprovalRequestId('  req_789  ')).toEqual({
        success: true,
        requestId: 'req_789',
      })
    })

    it('returns a bad request response for blank request ids', () => {
      const result = validateApprovalRequestId('   ')

      expect(result.success).toBe(false)
      if (!result.success) {
        expect(result.response.status).toBe(400)
        void expect(result.response.json()).resolves.toEqual({
          status: 'error',
          error: {
            code: 'BAD_REQUEST',
            message: 'requestId is required',
          },
        })
      }
    })
  })
})
