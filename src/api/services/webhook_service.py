"""
Webhook delivery service for MUTX.

Handles:
- Webhook registration CRUD
- Event delivery with retry logic
- Signature generation for payload verification
"""

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import random
import socket
import ssl
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional
from urllib.parse import urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.models import Webhook, WebhookDeliveryLog
from src.api.security import decrypt_secret_value

logger = logging.getLogger(__name__)

# Delivery retry configuration (MC v2.0 parity)
MAX_RETRIES = 5
BACKOFF_SCHEDULE = [30, 300, 1800, 7200, 28800]  # 30s, 5m, 30m, 2h, 8h
TIMEOUT_SECONDS = 30
DNS_RESOLUTION_TIMEOUT_SECONDS = 5
CIRCUIT_BREAKER_THRESHOLD = MAX_RETRIES  # Open circuit after this many consecutive failures
_RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

# Webhooks are an arbitrary outbound request primitive, so keep the accepted
# transport surface deliberately small. Supporting additional ports should be
# an explicit product decision accompanied by an egress-policy review.
ALLOWED_WEBHOOK_PORTS = frozenset({443})
_BLOCKED_IPV4_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.31.196.0/24",
        "192.52.193.0/24",
        "192.88.99.0/24",
        "192.168.0.0/16",
        "192.175.48.0/24",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
    )
)
_NON_PUBLIC_DNS_SUFFIXES = (
    ".internal",
    ".invalid",
    ".local",
    ".localhost",
    ".test",
    ".home.arpa",
)


def _next_retry_delay(attempt: int) -> float:
    """Calculate retry delay with ±20% jitter (MC v2.0 pattern)."""
    base = BACKOFF_SCHEDULE[min(attempt, len(BACKOFF_SCHEDULE) - 1)]
    jitter = base * 0.2 * (random.random() * 2 - 1)  # ±20%
    return max(1.0, base + jitter)


class UnsafeWebhookDestinationError(ValueError):
    """Raised when a webhook destination points to a non-public network target."""


class WebhookDestinationResolutionError(UnsafeWebhookDestinationError):
    """Raised when DNS cannot be resolved within the delivery safety boundary."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class ValidatedWebhookDestination:
    """An original URL and the complete public address set allowed for one attempt."""

    original_url: str
    hostname: str
    port: int
    addresses: tuple[ipaddress.IPv4Address, ...]

    @property
    def resolved_ips(self) -> tuple[str, ...]:
        return tuple(address.compressed for address in self.addresses)


@dataclass(frozen=True)
class _WebhookDeliveryAttempt:
    success: bool
    status_code: Optional[int]
    error_message: Optional[str]
    duration_ms: int
    response_body: Optional[str]
    retryable: bool

    def public_result(
        self,
    ) -> tuple[bool, Optional[int], Optional[str], Optional[int], Optional[str]]:
        return (
            self.success,
            self.status_code,
            self.error_message,
            self.duration_ms,
            self.response_body,
        )


def generate_signature(payload: str, secret: str) -> str:
    """Generate HMAC-SHA256 signature for webhook payload."""
    if not secret:
        return ""
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _normalize_ip_address(
    value: str | ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    return ipaddress.ip_address(value)


def _assert_public_ip_address(
    value: str | ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    hostname: str,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        ip = _normalize_ip_address(value)
    except ValueError as exc:
        raise UnsafeWebhookDestinationError(
            f"Webhook destination '{hostname}' returned an invalid IP address"
        ) from exc

    # Production networks may use deployment-specific NAT64 or transition
    # prefixes which cannot be inferred reliably here. Until the egress layer
    # supplies an authoritative IPv6 policy, rejecting every IPv6 destination
    # is the only way to fail closed for mapped, site-local, transition, NAT64,
    # ULA, link-local, and other special forms.
    if isinstance(ip, ipaddress.IPv6Address):
        raise UnsafeWebhookDestinationError(
            f"Webhook destination '{hostname}' resolves to a non-public address"
        )

    blocked = (
        not ip.is_global
        or ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or any(ip in network for network in _BLOCKED_IPV4_NETWORKS)
    )

    if blocked:
        raise UnsafeWebhookDestinationError(
            f"Webhook destination '{hostname}' resolves to a non-public address"
        )
    return ip


def _parse_legacy_ipv4_address(hostname: str) -> ipaddress.IPv4Address | None:
    """Parse historical inet_aton forms so they cannot masquerade as DNS names."""

    parts = hostname.split(".")
    if not 1 <= len(parts) <= 4 or any(not part for part in parts):
        return None

    def parse_part(part: str) -> int:
        if part.lower().startswith("0x"):
            return int(part[2:], 16)
        if len(part) > 1 and part.startswith("0"):
            return int(part[1:] or "0", 8)
        return int(part, 10)

    try:
        numbers = [parse_part(part) for part in parts]
    except ValueError:
        return None

    widths = {
        1: (32,),
        2: (8, 24),
        3: (8, 8, 16),
        4: (8, 8, 8, 8),
    }[len(numbers)]
    if any(number < 0 or number >= (1 << width) for number, width in zip(numbers, widths)):
        return None

    value = 0
    for number, width in zip(numbers, widths):
        value = (value << width) | number
    return ipaddress.IPv4Address(value)


def _validate_dns_hostname(hostname: str) -> str:
    if any(ord(character) > 127 for character in hostname):
        raise UnsafeWebhookDestinationError(
            "Webhook hostname must use an unambiguous ASCII/IDNA representation"
        )
    if "%" in hostname or "\\" in hostname:
        raise UnsafeWebhookDestinationError("Webhook hostname contains ambiguous encoding")

    canonical_hostname = hostname.lower()
    if canonical_hostname.endswith("."):
        raise UnsafeWebhookDestinationError("Webhook hostname must not end with a dot")
    if canonical_hostname == "localhost" or canonical_hostname.endswith(_NON_PUBLIC_DNS_SUFFIXES):
        raise UnsafeWebhookDestinationError(
            f"Webhook destination '{hostname}' resolves to a non-public address"
        )
    if "." not in canonical_hostname:
        raise UnsafeWebhookDestinationError(
            "Webhook hostname must be a fully qualified domain name"
        )
    if len(canonical_hostname) > 253:
        raise UnsafeWebhookDestinationError("Webhook hostname is too long")

    labels = canonical_hostname.split(".")
    if any(label.startswith("xn--") for label in labels):
        raise UnsafeWebhookDestinationError(
            "Webhook hostname must not use an internationalized IDNA label"
        )
    if any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or not all(
            character.isascii() and (character.isalnum() or character == "-") for character in label
        )
        for label in labels
    ):
        raise UnsafeWebhookDestinationError("Webhook hostname is not a valid DNS name")
    return canonical_hostname


def _parse_webhook_url(url: str) -> tuple[str, int]:
    if url != url.strip() or any(ord(character) < 32 or ord(character) == 127 for character in url):
        raise UnsafeWebhookDestinationError(
            "Webhook URL must not contain whitespace or control characters"
        )
    if "\\" in url:
        raise UnsafeWebhookDestinationError("Webhook URL must not contain backslashes")

    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise UnsafeWebhookDestinationError("Webhook URL is malformed") from exc

    if parsed.scheme.lower() != "https":
        raise UnsafeWebhookDestinationError(
            "Webhook URL must use HTTPS (https://); other schemes are not allowed"
        )
    if parsed.fragment:
        raise UnsafeWebhookDestinationError("Webhook URL must not include a fragment")
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        raise UnsafeWebhookDestinationError("Webhook URL must not include user information")
    if parsed.netloc.endswith(":"):
        raise UnsafeWebhookDestinationError("Webhook URL contains an invalid port")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeWebhookDestinationError("Webhook URL must include a hostname")
    try:
        parsed_port = parsed.port
    except ValueError as exc:
        raise UnsafeWebhookDestinationError("Webhook URL contains an invalid port") from exc
    port = 443 if parsed_port is None else parsed_port
    if port not in ALLOWED_WEBHOOK_PORTS:
        raise UnsafeWebhookDestinationError("Webhook URL must use the standard HTTPS port 443")

    if parsed.netloc.startswith("["):
        closing_bracket = parsed.netloc.find("]")
        port_suffix = parsed.netloc[closing_bracket + 1 :]
    else:
        _, separator, port_text = parsed.netloc.rpartition(":")
        port_suffix = f":{port_text}" if separator else ""
    if port_suffix not in {"", ":443"}:
        raise UnsafeWebhookDestinationError(
            "Webhook URL port must use the canonical HTTPS representation ':443'"
        )

    return hostname, port


async def resolve_webhook_destination_ips(hostname: str, port: int) -> tuple[str, ...]:
    loop = asyncio.get_running_loop()
    try:
        addrinfo = await asyncio.wait_for(
            loop.getaddrinfo(
                hostname,
                port,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            ),
            timeout=DNS_RESOLUTION_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise WebhookDestinationResolutionError(
            f"Webhook destination '{hostname}' resolution timed out",
            retryable=True,
        ) from exc
    except socket.gaierror as exc:
        retryable = exc.errno == socket.EAI_AGAIN
        raise WebhookDestinationResolutionError(
            f"Webhook destination '{hostname}' could not be resolved",
            retryable=retryable,
        ) from exc
    except OSError as exc:
        raise WebhookDestinationResolutionError(
            f"Webhook destination '{hostname}' could not be resolved",
            retryable=True,
        ) from exc

    resolved_ips = {sockaddr[0] for _, _, _, _, sockaddr in addrinfo if sockaddr and sockaddr[0]}
    if not resolved_ips:
        raise WebhookDestinationResolutionError(
            f"Webhook destination '{hostname}' returned no addresses",
            retryable=True,
        )

    return tuple(resolved_ips)


async def ensure_safe_webhook_destination(url: str) -> ValidatedWebhookDestination:
    """Resolve every answer and return the complete address set allowed for one attempt."""

    hostname, port = _parse_webhook_url(url)
    try:
        parsed_ip = _normalize_ip_address(hostname)
    except ValueError:
        parsed_ip = None

    if parsed_ip is not None:
        public_ips = (_assert_public_ip_address(parsed_ip, hostname=hostname),)
        canonical_hostname = parsed_ip.compressed
    else:
        if _parse_legacy_ipv4_address(hostname) is not None:
            raise UnsafeWebhookDestinationError(
                "Webhook hostname uses an ambiguous or non-canonical IP address"
            )
        canonical_hostname = _validate_dns_hostname(hostname)
        resolved_ips = await resolve_webhook_destination_ips(canonical_hostname, port)
        public_ips = tuple(
            _assert_public_ip_address(resolved_ip, hostname=canonical_hostname)
            for resolved_ip in resolved_ips
        )

    sorted_ips = tuple(sorted(set(public_ips), key=int))

    return ValidatedWebhookDestination(
        original_url=url,
        hostname=canonical_hostname,
        port=port,
        addresses=sorted_ips,
    )


class _PinnedWebhookResolver(AbstractResolver):
    """Expose only the public addresses approved for this delivery attempt."""

    def __init__(self, destination: ValidatedWebhookDestination) -> None:
        self._hostname = destination.hostname
        self._port = destination.port
        self._addresses = destination.addresses

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: socket.AddressFamily = socket.AF_INET,
    ) -> list[ResolveResult]:
        if host.lower() != self._hostname or port != self._port:
            raise OSError("Refusing to resolve an unvalidated webhook authority")

        results: list[ResolveResult] = []
        for address in self._addresses:
            if family not in {socket.AF_UNSPEC, socket.AF_INET}:
                continue
            results.append(
                ResolveResult(
                    hostname=host,
                    host=address.compressed,
                    port=port,
                    family=socket.AF_INET,
                    proto=socket.IPPROTO_TCP,
                    flags=0,
                )
            )
        return results

    async def close(self) -> None:
        return None


def _pinned_webhook_socket_factory(
    allowed_addresses: Iterable[ipaddress.IPv4Address],
    allowed_port: int,
):
    """Create sockets only for the exact address set validated for this attempt."""

    allowed = frozenset(allowed_addresses)

    def create_socket(addr_info: tuple) -> socket.socket:
        family, sock_type, proto, _, sockaddr = addr_info
        if (
            family != socket.AF_INET
            or sock_type != socket.SOCK_STREAM
            or proto not in {0, socket.IPPROTO_TCP}
        ):
            raise OSError("Refusing unsupported webhook socket parameters")
        try:
            address = ipaddress.ip_address(sockaddr[0])
            port = int(sockaddr[1])
        except (TypeError, ValueError, IndexError) as exc:
            raise OSError("Refusing malformed webhook connection address") from exc
        if address not in allowed or port != allowed_port:
            raise OSError("Refusing webhook connection to an unvalidated address")
        return socket.socket(family=family, type=sock_type, proto=proto)

    return create_socket


def create_webhook_client_session(
    destination: ValidatedWebhookDestination,
    *,
    ssl_context: ssl.SSLContext | None = None,
) -> aiohttp.ClientSession:
    """Create one proxy-free, non-reusable, destination-pinned HTTPS session."""

    connector = aiohttp.TCPConnector(
        resolver=_PinnedWebhookResolver(destination),
        socket_factory=_pinned_webhook_socket_factory(
            destination.addresses,
            destination.port,
        ),
        use_dns_cache=False,
        force_close=True,
        limit=1,
        limit_per_host=1,
        ssl=ssl_context if ssl_context is not None else True,
    )
    return aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDS),
        trust_env=False,
    )


async def _send_pinned_webhook_request(
    destination: ValidatedWebhookDestination,
    payload_json: str,
    headers: dict[str, str],
    *,
    ssl_context: ssl.SSLContext | None = None,
) -> tuple[int, str]:
    """Send against the original URL so aiohttp performs normal Host/SNI/TLS checks."""

    async with create_webhook_client_session(destination, ssl_context=ssl_context) as session:
        async with session.post(
            destination.original_url,
            data=payload_json.encode("utf-8"),
            headers=headers,
            allow_redirects=False,
        ) as response:
            body_bytes = await response.content.read(10001)
            response_body = body_bytes[:10000].decode(
                response.charset or "utf-8",
                errors="replace",
            )
            return response.status, response_body


async def _deliver_webhook_attempt(
    webhook: Webhook,
    event: str,
    payload: dict,
    delivery_id: uuid.UUID,
) -> _WebhookDeliveryAttempt:
    """Resolve, validate, and send one isolated webhook attempt."""

    url = webhook.url
    secret = decrypt_secret_value(webhook.secret)
    start_time = time.monotonic()

    # Prepare payload
    payload_json = json.dumps(
        {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "delivery_id": str(delivery_id),
            "data": payload,
        },
        default=str,
    )

    # Generate signature if secret is set
    headers = {
        "Connection": "close",
        "Content-Type": "application/json",
        "X-Webhook-Event": event,
        "X-Webhook-Delivery-Id": str(delivery_id),
    }

    if secret:
        signature = generate_signature(payload_json, secret)
        headers["X-Webhook-Signature"] = f"sha256={signature}"

    try:
        destination = await ensure_safe_webhook_destination(url)
    except WebhookDestinationResolutionError as exc:
        error_msg = str(exc)
        logger.warning("Webhook %s resolution failed: %s", webhook.id, error_msg)
        return _WebhookDeliveryAttempt(
            False,
            None,
            error_msg,
            int((time.monotonic() - start_time) * 1000),
            None,
            exc.retryable,
        )
    except UnsafeWebhookDestinationError as exc:
        error_msg = str(exc)
        logger.warning("Blocked unsafe webhook delivery %s: %s", webhook.id, error_msg)
        return _WebhookDeliveryAttempt(
            False,
            None,
            error_msg,
            int((time.monotonic() - start_time) * 1000),
            None,
            False,
        )

    try:
        status_code, response_body = await _send_pinned_webhook_request(
            destination,
            payload_json,
            headers,
        )
    except TimeoutError:
        error_msg = f"Timeout after {TIMEOUT_SECONDS}s"
        logger.warning("Webhook %s delivery timed out for event %s", webhook.id, event)
        return _WebhookDeliveryAttempt(
            False,
            None,
            error_msg,
            int((time.monotonic() - start_time) * 1000),
            None,
            True,
        )
    except (
        aiohttp.ClientConnectorCertificateError,
        aiohttp.ClientSSLError,
        aiohttp.ServerFingerprintMismatch,
    ) as exc:
        error_msg = f"TLS verification failed: {type(exc).__name__}"
        logger.warning("Webhook %s TLS verification failed", webhook.id)
        return _WebhookDeliveryAttempt(
            False,
            None,
            error_msg,
            int((time.monotonic() - start_time) * 1000),
            None,
            False,
        )
    except (aiohttp.ClientError, OSError) as exc:
        error_msg = f"Transport failed: {type(exc).__name__}"
        logger.warning("Webhook %s delivery transport failed: %s", webhook.id, type(exc).__name__)
        return _WebhookDeliveryAttempt(
            False,
            None,
            error_msg,
            int((time.monotonic() - start_time) * 1000),
            None,
            True,
        )
    except Exception as exc:
        error_msg = f"Unexpected error: {type(exc).__name__}"
        logger.exception("Unexpected webhook %s delivery failure", webhook.id)
        return _WebhookDeliveryAttempt(
            False,
            None,
            error_msg,
            int((time.monotonic() - start_time) * 1000),
            None,
            False,
        )

    duration_ms = int((time.monotonic() - start_time) * 1000)
    if 200 <= status_code < 300:
        logger.info("Webhook %s delivered event %s successfully", webhook.id, event)
        return _WebhookDeliveryAttempt(
            True,
            status_code,
            None,
            duration_ms,
            response_body,
            False,
        )

    error_msg = f"HTTP {status_code}: {response_body[:200]}"
    logger.warning("Webhook %s delivery failed: %s", webhook.id, error_msg)
    return _WebhookDeliveryAttempt(
        False,
        status_code,
        error_msg,
        duration_ms,
        response_body,
        status_code in _RETRYABLE_HTTP_STATUSES,
    )


async def deliver_webhook(
    webhook: Webhook,
    event: str,
    payload: dict,
    delivery_id: uuid.UUID,
) -> tuple[bool, Optional[int], Optional[str], Optional[int], Optional[str]]:
    """Attempt one freshly resolved and transport-pinned webhook delivery."""

    return (await _deliver_webhook_attempt(webhook, event, payload, delivery_id)).public_result()


async def deliver_webhook_with_retry(
    db: AsyncSession,
    webhook: Webhook,
    event: str,
    payload: dict,
    parent_delivery_id: Optional[uuid.UUID] = None,
) -> bool:
    """
    Deliver webhook with retry logic, circuit breaker, and exponential backoff.

    Retries up to MAX_RETRIES times with increasing delays + jitter.
    Tracks consecutive failures and opens the circuit breaker when threshold is reached.
    """
    if db.bind is None:
        raise RuntimeError("Database session is not bound")

    isolated_session_factory = async_sessionmaker(
        db.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with isolated_session_factory() as isolated_db:
        refreshed_webhook = await isolated_db.get(Webhook, webhook.id)
        if not refreshed_webhook or not refreshed_webhook.is_active:
            logger.info(f"Webhook {webhook.id} is inactive, skipping delivery")
            return False

        # Circuit breaker check: skip if already open
        if refreshed_webhook.consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
            logger.warning(
                f"Circuit breaker open for webhook {webhook.id} "
                f"({refreshed_webhook.consecutive_failures} consecutive failures). "
                f"Skipping delivery."
            )
            return False

        delivery_id = uuid.uuid4()
        delivery_log = WebhookDeliveryLog(
            id=delivery_id,
            webhook_id=refreshed_webhook.id,
            event=event,
            payload=json.dumps(payload, default=str),
            parent_delivery_id=parent_delivery_id,
        )
        isolated_db.add(delivery_log)
        await isolated_db.commit()

        attempts_made = 0
        for attempt in range(MAX_RETRIES):
            attempts_made = attempt + 1
            result = await _deliver_webhook_attempt(
                refreshed_webhook,
                event,
                payload,
                delivery_id,
            )

            if result.success:
                delivery_log.success = True
                delivery_log.status_code = result.status_code
                delivery_log.duration_ms = result.duration_ms
                delivery_log.response_body = result.response_body or ""
                delivery_log.delivered_at = datetime.now(timezone.utc)

                # Reset circuit breaker on success
                refreshed_webhook.consecutive_failures = 0
                await isolated_db.commit()
                return True

            delivery_log.attempts = attempt + 1
            delivery_log.status_code = result.status_code
            delivery_log.error_message = result.error_message
            delivery_log.duration_ms = result.duration_ms
            delivery_log.response_body = result.response_body or ""
            await isolated_db.commit()

            if not result.retryable:
                break
            if attempt < MAX_RETRIES - 1:
                delay = _next_retry_delay(attempt)
                logger.info(
                    f"Retrying webhook delivery in {delay:.1f}s (attempt {attempt + 2}/{MAX_RETRIES})"
                )
                await asyncio.sleep(delay)

        # All retries exhausted — increment consecutive failures
        refreshed_webhook.consecutive_failures += 1
        await isolated_db.commit()

        logger.error(
            "Webhook %s delivery failed after %s attempts for event %s",
            refreshed_webhook.id,
            attempts_made,
            event,
        )
        return False


async def trigger_webhook_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    event: str,
    payload: dict,
) -> int:
    """
    Trigger a webhook event to all active webhooks subscribed to the event.

    Returns:
        Number of successful deliveries
    """
    # Get active webhooks for the owning user only
    result = await db.execute(select(Webhook).where(Webhook.is_active, Webhook.user_id == user_id))
    webhooks = result.scalars().all()

    # Filter webhooks by event subscription
    matching_webhooks = []
    for webhook in webhooks:
        events = webhook.events or []
        # Check if event matches subscription (supports wildcards)
        for subscribed_event in events:
            if subscribed_event == "*":
                matching_webhooks.append(webhook)
                break
            elif subscribed_event.endswith(".*"):
                prefix = subscribed_event[:-1]  # Remove trailing *
                if event.startswith(prefix):
                    matching_webhooks.append(webhook)
                    break
            elif subscribed_event == event:
                matching_webhooks.append(webhook)
                break

    if not matching_webhooks:
        logger.debug(f"No webhooks subscribed to event: {event}")
        return 0

    # Deduplicate webhooks (in case of overlapping subscriptions)
    unique_webhooks = list({w.id: w for w in matching_webhooks}.values())

    logger.info(f"Delivering event '{event}' to {len(unique_webhooks)} webhooks")

    success_count = 0
    tasks = [deliver_webhook_with_retry(db, webhook, event, payload) for webhook in unique_webhooks]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Webhook delivery exception: {result}")
        elif result:
            success_count += 1

    logger.info(f"Event '{event}' delivered to {success_count}/{len(unique_webhooks)} webhooks")
    return success_count


# Helper function to trigger common events
async def trigger_agent_status_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    agent_id: uuid.UUID,
    old_status: str,
    new_status: str,
    agent_name: str,
):
    """Trigger agent.status event."""
    await trigger_webhook_event(
        db,
        user_id,
        "agent.status",
        {
            "agent_id": str(agent_id),
            "agent_name": agent_name,
            "old_status": old_status,
            "new_status": new_status,
        },
    )


async def trigger_deployment_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    deployment_id: uuid.UUID,
    agent_id: uuid.UUID,
    event_type: str,
    status: Optional[str] = None,
):
    """Trigger deployment event."""
    await trigger_webhook_event(
        db,
        user_id,
        "deployment.event",
        {
            "deployment_id": str(deployment_id),
            "agent_id": str(agent_id),
            "event_type": event_type,
            "status": status,
        },
    )
