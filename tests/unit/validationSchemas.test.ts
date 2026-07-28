import { schemas } from '../../app/api/_lib/validation'

describe('validation schemas', () => {
  describe('login schema', () => {
    it('accepts valid login credentials', async () => {
      const result = await schemas.login.safeParseAsync({
        email: 'test@example.com',
        password: 'password123',
      })
      expect(result.success).toBe(true)
      if (result.success) {
        expect(result.data.email).toBe('test@example.com')
        expect(result.data.password).toBe('password123')
      }
    })

    it('rejects invalid email format', async () => {
      const result = await schemas.login.safeParseAsync({
        email: 'not-an-email',
        password: 'password123',
      })
      expect(result.success).toBe(false)
    })

    it('rejects empty password', async () => {
      const result = await schemas.login.safeParseAsync({
        email: 'test@example.com',
        password: '',
      })
      expect(result.success).toBe(false)
    })
  })

  describe('register schema', () => {
    it('accepts valid registration data', async () => {
      const result = await schemas.register.safeParseAsync({
        email: 'newuser@example.com',
        password: 'securepassword',
        name: 'New User',
        return_path: '/dashboard/runs?status=held#current',
      })
      expect(result.success).toBe(true)
      if (result.success) {
        expect(result.data.return_path).toBe('/dashboard/runs?status=held#current')
      }
    })

    it('rejects short password', async () => {
      const result = await schemas.register.safeParseAsync({
        email: 'test@example.com',
        password: 'short',
        name: 'Test User',
      })
      expect(result.success).toBe(false)
    })

    it('rejects missing name', async () => {
      const result = await schemas.register.safeParseAsync({
        email: 'test@example.com',
        password: 'password123',
        name: '',
      })
      expect(result.success).toBe(false)
    })
  })

  describe('lead schema', () => {
    it('accepts minimal lead submission with email only', async () => {
      const result = await schemas.lead.safeParseAsync({
        email: 'lead@example.com',
      })
      expect(result.success).toBe(true)
    })

    it('accepts full lead submission', async () => {
      const result = await schemas.lead.safeParseAsync({
        email: 'lead@example.com',
        name: 'Test Lead',
        company: 'Test Corp',
        message: 'Interested in your product',
        source: 'contact-page',
      })
      expect(result.success).toBe(true)
    })

    it('rejects missing email', async () => {
      const result = await schemas.lead.safeParseAsync({
        name: 'Missing Email',
      })
      expect(result.success).toBe(false)
    })

    it('rejects invalid email format', async () => {
      const result = await schemas.lead.safeParseAsync({
        email: 'not-email',
      })
      expect(result.success).toBe(false)
    })
  })

  describe('apiKeyCreate schema', () => {
    it('accepts valid API key creation request', async () => {
      const result = await schemas.apiKeyCreate.safeParseAsync({
        name: 'my-api-key',
      })
      expect(result.success).toBe(true)
    })

    it('accepts API key with expiry', async () => {
      const result = await schemas.apiKeyCreate.safeParseAsync({
        name: 'my-api-key',
        expires_in_days: 30,
      })
      expect(result.success).toBe(true)
    })

    it('rejects empty key name', async () => {
      const result = await schemas.apiKeyCreate.safeParseAsync({
        name: '',
      })
      expect(result.success).toBe(false)
    })

    it('rejects negative expiry', async () => {
      const result = await schemas.apiKeyCreate.safeParseAsync({
        name: 'my-api-key',
        expires_in_days: -1,
      })
      expect(result.success).toBe(false)
    })

    it('rejects expiry over 365 days', async () => {
      const result = await schemas.apiKeyCreate.safeParseAsync({
        name: 'my-api-key',
        expires_in_days: 400,
      })
      expect(result.success).toBe(false)
    })
  })

  describe('agentCreate schema', () => {
    it.each([
      ['minimal payload', { name: 'my-agent' }],
      [
        'backend field limits and openclaw config',
        {
          name: 'a'.repeat(255),
          description: 'd'.repeat(1000),
          type: 'openclaw',
          config: { runtime: 'personal_assistant' },
        },
      ],
      ['serialized backend config', { name: 'serialized', config: '{"model":"gpt-4o"}' }],
    ])('accepts %s', async (_label, payload) => {
      await expect(schemas.agentCreate.safeParseAsync(payload)).resolves.toMatchObject({
        success: true,
      })
    })

    it.each([
      ['empty name', { name: '' }],
      ['256-character name', { name: 'a'.repeat(256) }],
      ['1001-character description', { name: 'agent', description: 'd'.repeat(1001) }],
      ['unsupported type', { name: 'agent', type: 'other' }],
      ['unsupported top-level config field', { name: 'agent', model: 'gpt-4o' }],
    ])('rejects %s', async (_label, payload) => {
      await expect(schemas.agentCreate.safeParseAsync(payload)).resolves.toMatchObject({
        success: false,
      })
    })
  })

  describe('deploymentCreate schema', () => {
    const agentId = '123e4567-e89b-42d3-a456-426614174000'

    it.each([
      ['default replicas', { agent_id: agentId }],
      ['one replica', { agent_id: agentId, replicas: 1 }],
      ['ten replicas', { agent_id: agentId, replicas: 10 }],
    ])('accepts %s', async (_label, payload) => {
      await expect(schemas.deploymentCreate.safeParseAsync(payload)).resolves.toMatchObject({
        success: true,
      })
    })

    it.each([
      ['zero replicas', { agent_id: agentId, replicas: 0 }],
      ['eleven replicas', { agent_id: agentId, replicas: 11 }],
      ['silently ignored environment', { agent_id: agentId, environment: 'production' }],
      ['silently ignored config', { agent_id: agentId, config: { region: 'eu' } }],
    ])('rejects %s', async (_label, payload) => {
      await expect(schemas.deploymentCreate.safeParseAsync(payload)).resolves.toMatchObject({
        success: false,
      })
    })
  })

  describe('webhook schemas', () => {
    const urlAtLength = (length: number) =>
      `https://example.com/${'a'.repeat(length - 'https://example.com/'.length)}`

    it.each([
      [
        'create fields at backend limits',
        schemas.webhookCreate,
        {
          url: urlAtLength(512),
          name: 'n'.repeat(120),
          events: ['agent.status'],
          secret: 's'.repeat(64),
          is_active: true,
        },
      ],
      ['create default events', schemas.webhookCreate, { url: 'https://example.com/hook' }],
      [
        'update name and circuit reset',
        schemas.webhookUpdate,
        { url: urlAtLength(512), name: 'n'.repeat(120), reset_circuit: true },
      ],
    ])('accepts %s', async (_label, schema, payload) => {
      await expect(schema.safeParseAsync(payload)).resolves.toMatchObject({ success: true })
    })

    it.each([
      ['513-character create URL', schemas.webhookCreate, { url: urlAtLength(513) }],
      [
        '121-character create name',
        schemas.webhookCreate,
        { url: 'https://example.com/hook', name: 'n'.repeat(121) },
      ],
      [
        '65-character create secret',
        schemas.webhookCreate,
        { url: 'https://example.com/hook', secret: 's'.repeat(65) },
      ],
      ['513-character update URL', schemas.webhookUpdate, { url: urlAtLength(513) }],
      ['121-character update name', schemas.webhookUpdate, { name: 'n'.repeat(121) }],
      ['unsupported update secret', schemas.webhookUpdate, { secret: 'replacement' }],
    ])('rejects %s', async (_label, schema, payload) => {
      await expect(schema.safeParseAsync(payload)).resolves.toMatchObject({ success: false })
    })
  })
})
