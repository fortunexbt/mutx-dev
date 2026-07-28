---
description: Step-by-step guide to integrating MUTX webhooks into your application.
icon: plug
---

# Webhook Integration Guide

This guide walks you through integrating MUTX webhooks into your application. Webhooks allow your app to receive real-time notifications when events occur in MUTX.

## Quick Start

### 1. Register a Webhook

```bash
# Using the CLI
mutx webhooks list

# Create via API
curl -X POST "https://api.mutx.dev/v1/webhooks/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-app.com/webhooks/mutx",
    "events": ["agent.*", "deployment.*"]
  }'
```

### 2. Verify It's Working

```bash
# Check your webhook was created
mutx webhooks list

# Send a test event
curl -X POST "https://api.mutx.dev/v1/webhooks/WEBHOOK_ID/test" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Using the SDK

### Create a Webhook

```python
from mutx import MutxClient

client = MutxClient(api_key="your-api-key")

# Create webhook
webhook = client.webhooks.create(
    url="https://your-app.com/webhooks/mutx",
    events=["agent.*", "deployment.*"],
    secret="your-webhook-secret",  # Optional: for signature verification
    is_active=True
)

print(f"Created webhook: {webhook.id}")
```

### List and Manage Webhooks

```python
# List all webhooks
webhooks = client.webhooks.list(limit=10)

for wh in webhooks:
    print(f"{wh.id} -> {wh.url} (active: {wh.is_active})")

# Get specific webhook
webhook = client.webhooks.get(webhook_id="...")

# Update webhook
updated = client.webhooks.update(
    webhook_id="...",
    url="https://new-url.com/webhook",
    is_active=False
)

# Delete webhook
client.webhooks.delete(webhook_id="...")
```

### Check Delivery History

```python
# Get delivery attempts
deliveries = client.webhooks.get_deliveries(
    webhook_id="...",
    limit=20,
    event="agent.status",
    success=False  # Only failed deliveries
)

for d in deliveries:
    print(f"{d.event} - success: {d.success}, attempts: {d.attempts}")
    if not d.success:
        print(f"  Error: {d.error_message}")
```

### Async Usage

```python
import asyncio
from mutx import AsyncMutxClient

async def manage_webhooks():
    client = AsyncMutxClient(api_key="your-api-key")

    # Create webhook
    webhook = await client.webhooks.acreate(
        url="https://your-app.com/webhooks/mutx",
        events=["agent.*"]
    )

    # List webhooks
    webhooks = await client.webhooks.alist()

    await client.close()

asyncio.run(manage_webhooks())
```

## Handling Webhook Payloads

### Example: Express.js Handler

```javascript
const express = require('express');
const crypto = require('crypto');

const app = express();
app.use(express.json());

// Verify HMAC signature
function verifySignature(payload, signature, secret) {
  if (!signature || !secret) return true; // Skip if no secret configured

  const hmac = crypto.createHmac('sha256', secret);
  const digest = 'sha256=' + hmac.update(payload).digest('hex');

  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(digest)
  );
}

app.post('/webhooks/mutx', (req, res) => {
  const signature = req.headers['x-webhook-signature'];

  if (!verifySignature(JSON.stringify(req.body), signature, process.env.WEBHOOK_SECRET)) {
    return res.status(401).json({ error: 'Invalid signature' });
  }

  const { event, data } = req.body;

  switch (event) {
    case 'agent.status':
      console.log(`Agent ${data.agent_id} status: ${data.new_status}`);
      break;
    case 'deployment.created':
      console.log(`Deployment created: ${data.deployment_id}`);
      break;
    case 'deployment.failed':
      console.log(`Deployment failed: ${data.deployment_id}`);
      // Trigger alerting, rollback, etc.
      break;
  }

  res.status(200).json({ received: true });
});

app.listen(3000, () => console.log('Webhook listener running'));
```

### Example: Python Flask Handler

```python
import hmac
import hashlib
from flask import Flask, request, jsonify

app = Flask(__name__)
WEBHOOK_SECRET = "your-webhook-secret"

def verify_signature(payload: bytes, signature: str) -> bool:
    if not signature or not WEBHOOK_SECRET:
        return True

    expected = f"sha256={hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()}"

    return hmac.compare_digest(signature, expected)

@app.route('/webhooks/mutx', methods=['POST'])
def handle_webhook():
    payload = request.get_data()
    signature = request.headers.get('X-Webhook-Signature')

    if not verify_signature(payload, signature):
        return jsonify({'error': 'Invalid signature'}), 401

    event = request.json.get('event')
    data = request.json.get('data', {})

    if event == 'agent.status':
        agent_id = data.get('agent_id')
        new_status = data.get('new_status')
        print(f"Agent {agent_id} status: {new_status}")

    elif event == 'deployment.failed':
        deployment_id = data.get('deployment_id')
        error = data.get('error')
        print(f"Deployment {deployment_id} failed: {error}")
        # Trigger alerting, rollback, etc.

    return jsonify({'received': True}), 200

if __name__ == '__main__':
    app.run(port=3000)
```

## Event Types Reference

| Event | Description | Payload Fields |
|-------|-------------|-----------------|
| `agent.started` | Agent started running | `agent_id`, `node_id` |
| `agent.stopped` | Agent stopped | `agent_id`, `node_id`, `reason` |
| `agent.crashed` | Agent crashed | `agent_id`, `node_id`, `error` |
| `agent.heartbeat` | Periodic heartbeat | `agent_id`, `status`, `node_id` |
| `agent.status` | Status changed | `agent_id`, `new_status`, `old_status` |
| `deployment.created` | Deployment created | `deployment_id`, `agent_id` |
| `deployment.updated` | Deployment updated | `deployment_id`, `changes` |
| `deployment.failed` | Deployment failed | `deployment_id`, `error` |
| `deployment.rolled_back` | Rolled back | `deployment_id`, `reason` |
| `metrics.report` | Metrics report | `agent_id`, `metrics` |

## Security Best Practices

1. **Always verify signatures** - Use the `secret` parameter when creating webhooks and verify the `X-Webhook-Signature` header
2. **Use HTTPS** - Never expose webhooks over plain HTTP in production
3. **Implement idempotency** - Webhooks may be retried up to 3 times; design handlers to handle duplicates
4. **Log deliveries** - Use the delivery history API to monitor webhook health

## Troubleshooting

### Webhook Not Delivered

1. Check delivery history:
   ```bash
   mutx webhooks deliveries WEBHOOK_ID
   ```

2. Look for failed attempts and error messages

3. Verify your endpoint is accessible and responding

### Signature Verification Fails

- Ensure you're using the same secret you set when creating the webhook
- Check that your verification code matches the exact format: `sha256=...`
- Use constant-time comparison (`hmac.compare_digest` in Python)

### Testing Locally

Use a tool like `ngrok` to expose your local server:

```bash
# Terminal 1: Run your webhook server
python app.py

# Terminal 2: Tunnel with ngrok
ngrok http 3000

# Create webhook with the ngrok URL
curl -X POST "https://api.mutx.dev/v1/webhooks/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-ngrok-id.ngrok.io/webhooks/mutx",
    "events": ["*"]
  }'
```

## Next Steps

- Read the [API Reference](api/webhooks.md) for complete endpoint documentation
- Explore the [CLI commands](cli.md#webhooks) for webhook management
- Set up monitoring with the [OpenTelemetry guide](otel.md)
