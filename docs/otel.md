# OpenTelemetry Configuration Guide

This guide covers OpenTelemetry integration for distributed tracing in MUTX.

## Overview

MUTX supports OpenTelemetry distributed tracing. The API process configures its
active exporter at startup from `OTEL_*` environment variables. Separately, the
authenticated telemetry API stores a tenant-owned OTLP connectivity target and
reports bounded transport reachability; it does not hot-swap the process-wide
exporter.

## Dynamic telemetry backend registry

`GET`, `POST /v1/telemetry/config`, and `GET /v1/telemetry/health` require a
verified internal user with the persisted `ADMIN` role. Each principal can read
and update only its own durable configuration. A process restart does not erase
the saved target, and another administrator cannot observe or overwrite it.

Example request:

```http
POST /v1/telemetry/config
Authorization: Bearer <token>
Content-Type: application/json

{
  "otlp_endpoint": "https://otel.example.com:4317",
  "protocol": "grpc"
}
```

The API accepts only `http` and `https` URLs without credentials, query strings,
fragments, or scoped IPv6 addresses. The hostname must resolve entirely to
public, globally routable addresses. Loopback, private, carrier-grade NAT,
link-local, site-local, reserved, multicast, IPv4-mapped, 6to4, Teredo, and
NAT64 targets are rejected. DNS and connect work have short deadlines and a
bounded address count.

Health is a TCP/TLS reachability probe, not proof that the collector accepted
OTLP data. It re-resolves the hostname on every request and connects directly to
the validated address, so HTTP redirects and environment proxies are not used.
The response separates the saved target from runtime state:

- `configured` means a target is durably saved for the caller.
- `endpoint_reachable` means the bounded TCP/TLS probe connected.
- `otel_enabled` and `exporter_type` describe the active API process.
- `runtime_applied` is `false`; set deployment `OTEL_*` variables and restart to
  apply an exporter change.

Private in-cluster collectors such as `localhost` or Kubernetes service names
must be configured through trusted deployment environment variables, not this
user-influenced API surface.

## Quick Start

### 1. Install Dependencies

Install the repository requirements, which include the OpenTelemetry API, SDK,
FastAPI instrumentation, and exporters used by MUTX:

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Add these to your `.env` file:

```bash
OTEL_SERVICE_NAME=mutx-api

# Choose the startup exporter (console, otlp, or zipkin)
OTEL_TRACES_EXPORTER=otlp

# For the OTLP gRPC exporter
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# For Zipkin
OTEL_EXPORTER_ZIPKIN_ENDPOINT=http://localhost:9411/api/v2/spans
```

### 3. Application initialization

`src.api.main.create_app()` initializes the tracer provider and instruments the
FastAPI application. Do not initialize a second provider in route code.

## Environment Variable Configuration

### General Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `OTEL_SERVICE_NAME` | Service name for traces | `mutx-api` |

### Exporter Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `OTEL_TRACES_EXPORTER` | Exporter type: `console`, `otlp`, or `zipkin` | `console` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP gRPC endpoint | `http://localhost:4317` |
| `OTEL_EXPORTER_ZIPKIN_ENDPOINT` | Zipkin API endpoint | `http://localhost:9411` |

### Sampling Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `OTEL_TRACES_SAMPLER` | Sampler type: `always_on`, `always_off`, or `parentbased_traceidratio` | `parentbased_traceidratio` |
| `OTEL_TRACES_SAMPLER_ARG` | Ratio used by the parent-based ratio sampler | `0.1` |

## Docker Compose Examples

### Option 1: Grafana Tempo + Grafana + Prometheus

This stack provides full observability with Tempo for traces, Prometheus for metrics, and Grafana for visualization.

```bash
cd infrastructure/docker
docker-compose -f otel-compose.yml up -d tempo
```

Or use the Makefile:

```bash
make up-otel-tempo
```

Set secure Grafana credentials before starting:

```bash
export GRAFANA_ADMIN_USER=mutx_admin
export GRAFANA_ADMIN_PASSWORD='<strong-password>'
```

Access:
- Grafana: http://localhost:3001 (traces via Tempo)
- Tempo: http://localhost:3200

### Option 2: Jaeger (All-in-One)

Quick setup for development:

```bash
docker-compose -f otel-compose.yml up -d jaeger
```

Access:
- Jaeger UI: http://localhost:16686

### Option 3: OpenTelemetry Collector + Prometheus + Grafana

Full stack with collector:

```bash
docker-compose -f otel-compose.yml up -d otel-collector
```

Set secure Grafana credentials before starting:

```bash
export GRAFANA_ADMIN_USER=mutx_admin
export GRAFANA_ADMIN_PASSWORD='<strong-password>'
```

Access:
- Grafana: http://localhost:3002
- Prometheus: http://localhost:9091
- OTLP Receiver: http://localhost:4318

See `infrastructure/docker/otel-compose.yml` for complete configuration.

## Troubleshooting

### Common Issues

#### No traces appearing

1. **Check the startup exporter setting**
   ```bash
   echo $OTEL_TRACES_EXPORTER
   ```

2. **Verify network connectivity**
   ```bash
   curl http://localhost:4318/v1/traces
   ```

3. **Check collector/receiver logs**
   ```bash
   docker logs mutx-otel-collector
   docker logs mutx-tempo
   ```

4. **Verify exporter endpoint**
   ```bash
   # For OTLP
   echo $OTEL_EXPORTER_OTLP_ENDPOINT

   # For Jaeger
   curl -s http://localhost:14268/api/traces/status
   ```

#### High memory usage

Reduce sampling rate:

```bash
OTEL_TRACES_SAMPLER=traceidratio
OTEL_TRACES_SAMPLER_ARG=0.1
```

#### Export timeouts

Increase timeout:

```bash
OTEL_EXPORTER_OTLP_TIMEOUT=30000
```

### Verification Commands

```bash
# Check if spans are being exported
curl -X POST http://localhost:4318/v1/traces   -H "Content-Type: application/json"   -d '{"resourceSpans":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"test"}}]}}]}'
```

### Checking Service Status

```python
from opentelemetry import trace

# Get tracer provider status
provider = trace.get_tracer_provider()
print(f"Tracer provider: {provider}")
```

## Redaction Configuration

By default, certain sensitive attributes are redacted from traces.

### Default Redacted Attributes

The following attributes are NOT exported to tracing backends:

- `http.request.body` - Request body content
- `http.response.body` - Response body content
- `token` - Authentication tokens
- `password` - Password fields
- `api_key` - API keys
- `authorization` - Authorization headers
- `x-api-key` - API key headers

### Custom Redaction

To customize redaction, set environment variables:

```bash
# Add custom sensitive keys
OTEL_REDACTED_ATTRIBUTES=secret,private_token,credit_card

# Disable all redaction (not recommended for production)
OTEL_REDACTION_ENABLED=false
```

### Implementing Custom Redaction

```python
from opentelemetry.sdk.trace import SpanProcessor

class RedactingSpanProcessor(SpanProcessor):
    SENSITIVE_ATTRIBUTES = {
        'password', 'token', 'api_key', 'authorization',
        'secret', 'private_token', 'credit_card'
    }

    def on_end(self, span):
        for key in list(span.attributes.keys()):
            if key.lower() in self.SENSITIVE_ATTRIBUTES:
                span.attributes[key] = '[REDACTED]'

# Add to your tracer provider
provider.add_span_processor(RedactingSpanProcessor())
```

### Redacting Specific Spans

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("sensitive-operation") as span:
    span.set_attribute("password", "[REDACTED]")
    span.set_attribute("api_key", "[REDACTED]")
```

## Integration Examples

### Flask Application

```python
from flask import Flask
from opentelemetry.instrumentation.flask import FlaskInstrumentor

app = Flask(__name__)

# Initialize after creating app
FlaskInstrumentor().instrument_app(app)
```

### FastAPI Application

```python
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

app = FastAPI()

FastAPIInstrumentor.instrument_app(app)
```

### Custom Span Creation

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

def process_data(data):
    with tracer.start_as_current_span("process_data") as span:
        span.set_attribute("data.type", type(data).__name__)
        span.set_attribute("data.size", len(data))

        # Nested span
        with tracer.start_as_current_span("transform") as transform_span:
            result = transform(data)
            transform_span.set_attribute("result.size", len(result))

        return result
```

## Related Files

- `infrastructure/docker/otel-compose.yml` - Docker Compose stacks
- `.env.example` - Environment variable template
- `src/api/metrics.py` - Prometheus metrics (complementary to traces)
