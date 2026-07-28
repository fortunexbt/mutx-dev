"""Tenant-scoped telemetry backend persistence and safe reachability probes.

The dynamic API stores an operator-selected OTLP target and can test transport
reachability. It deliberately does not mutate the process-wide OpenTelemetry
provider; applying a saved target requires a controlled service restart and
the corresponding ``OTEL_*`` deployment configuration.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
import ssl
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import SplitResult, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.telemetry_backend import TelemetryBackendConfig

TelemetryProtocol = Literal["grpc", "http"]

DNS_TIMEOUT_SECONDS = 1.0
CONNECT_TIMEOUT_SECONDS = 2.0
MAX_RESOLVED_ADDRESSES = 8

# IPv6 transition mechanisms can encode an IPv4 destination that differs from
# the apparently global IPv6 address. Block them instead of trying to validate
# two address families through a translator controlled outside this process.
_FORBIDDEN_IPV6_NETWORKS = (
    ipaddress.ip_network("::/96"),
    ipaddress.ip_network("::ffff:0:0/96"),
    ipaddress.ip_network("64:ff9b::/96"),  # RFC 6052 well-known NAT64 prefix
    ipaddress.ip_network("64:ff9b:1::/48"),  # RFC 8215 local-use NAT64 prefix
    ipaddress.ip_network("2001::/32"),  # Teredo
    ipaddress.ip_network("2002::/16"),  # 6to4
    ipaddress.ip_network("fec0::/10"),  # deprecated site-local space
)


class TelemetryEndpointError(ValueError):
    """The supplied endpoint is invalid, unsafe, or cannot be resolved safely."""


@dataclass(frozen=True)
class ResolvedTelemetryEndpoint:
    endpoint: str
    scheme: Literal["http", "https"]
    hostname: str
    port: int
    addresses: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]


def _normalized_url(endpoint: str) -> tuple[SplitResult, str, int]:
    if len(endpoint) > 2048:
        raise TelemetryEndpointError("OTLP endpoint is too long")
    if any(ord(character) < 32 or ord(character) == 127 for character in endpoint):
        raise TelemetryEndpointError("OTLP endpoint contains control characters")

    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError as exc:
        raise TelemetryEndpointError("OTLP endpoint is malformed") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise TelemetryEndpointError("OTLP endpoint must use http or https")
    if not parsed.hostname:
        raise TelemetryEndpointError("OTLP endpoint must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise TelemetryEndpointError("OTLP endpoint must not include credentials")
    if parsed.query or parsed.fragment:
        raise TelemetryEndpointError("OTLP endpoint must not include a query or fragment")

    raw_hostname = parsed.hostname.rstrip(".").lower()
    if "%" in raw_hostname:
        raise TelemetryEndpointError("Scoped IPv6 addresses are not allowed")

    try:
        hostname = str(ipaddress.ip_address(raw_hostname))
    except ValueError:
        try:
            hostname = raw_hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise TelemetryEndpointError("OTLP endpoint hostname is invalid") from exc
        if not hostname or len(hostname) > 253:
            raise TelemetryEndpointError("OTLP endpoint hostname is invalid")

    resolved_port = port or (443 if scheme == "https" else 80)
    if not 1 <= resolved_port <= 65535:
        raise TelemetryEndpointError("OTLP endpoint port is invalid")

    display_hostname = f"[{hostname}]" if ":" in hostname else hostname
    default_port = 443 if scheme == "https" else 80
    netloc = (
        display_hostname if resolved_port == default_port else f"{display_hostname}:{resolved_port}"
    )
    normalized = parsed._replace(scheme=scheme, netloc=netloc, query="", fragment="")
    return normalized, hostname, resolved_port


def _require_global_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> None:
    if (
        address.is_unspecified
        or address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or not address.is_global
    ):
        raise TelemetryEndpointError("OTLP endpoint resolves to a non-public address")

    if isinstance(address, ipaddress.IPv6Address):
        if address.is_site_local:
            raise TelemetryEndpointError("OTLP endpoint resolves to a site-local address")
        if address.ipv4_mapped is not None or address.sixtofour is not None or address.teredo:
            raise TelemetryEndpointError("IPv4 transition addresses are not allowed")
        if any(address in network for network in _FORBIDDEN_IPV6_NETWORKS):
            raise TelemetryEndpointError("IPv6 translation addresses are not allowed")


async def _getaddrinfo(hostname: str, port: int) -> list[tuple[Any, ...]]:
    loop = asyncio.get_running_loop()
    return await loop.getaddrinfo(
        hostname,
        port,
        family=socket.AF_UNSPEC,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )


async def _resolve_addresses(
    hostname: str,
    port: int,
) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            results = await asyncio.wait_for(
                _getaddrinfo(hostname, port),
                timeout=DNS_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise TelemetryEndpointError("OTLP endpoint DNS lookup timed out") from exc
        except OSError as exc:
            raise TelemetryEndpointError("OTLP endpoint hostname could not be resolved") from exc

        addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        for result in results:
            try:
                address = ipaddress.ip_address(result[4][0])
            except (IndexError, TypeError, ValueError) as exc:
                raise TelemetryEndpointError(
                    "OTLP endpoint returned an invalid DNS result"
                ) from exc
            if address not in addresses:
                addresses.append(address)

        if not addresses:
            raise TelemetryEndpointError("OTLP endpoint hostname returned no addresses")
        if len(addresses) > MAX_RESOLVED_ADDRESSES:
            raise TelemetryEndpointError("OTLP endpoint returned too many addresses")
    else:
        addresses = [literal]

    for address in addresses:
        _require_global_address(address)
    return tuple(addresses)


async def resolve_telemetry_endpoint(endpoint: str) -> ResolvedTelemetryEndpoint:
    """Normalize an endpoint and resolve every address within a fixed deadline."""
    parsed, hostname, port = _normalized_url(endpoint.strip())
    addresses = await _resolve_addresses(hostname, port)
    return ResolvedTelemetryEndpoint(
        endpoint=urlunsplit(parsed),
        scheme=parsed.scheme,  # type: ignore[arg-type]
        hostname=hostname,
        port=port,
        addresses=addresses,
    )


def _config_dict(config: TelemetryBackendConfig | None) -> dict[str, Any]:
    if config is None:
        return {
            "endpoint": None,
            "protocol": None,
            "configured": False,
            "updated_at": None,
        }
    return {
        "endpoint": config.endpoint,
        "protocol": config.protocol,
        "configured": True,
        "updated_at": config.updated_at,
    }


async def _get_config_record(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    for_update: bool = False,
) -> TelemetryBackendConfig | None:
    statement = select(TelemetryBackendConfig).where(TelemetryBackendConfig.owner_id == owner_id)
    if for_update:
        statement = statement.with_for_update()
    return (await db.execute(statement)).scalar_one_or_none()


async def get_current_config(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
) -> dict[str, Any]:
    """Load only the authenticated tenant's durable configuration."""
    return _config_dict(await _get_config_record(db, owner_id=owner_id))


async def configure_telemetry_backend(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    otlp_endpoint: str,
    protocol: TelemetryProtocol = "grpc",
) -> dict[str, Any]:
    """Validate and persist one tenant's OTLP connectivity target."""
    if protocol not in ("grpc", "http"):
        raise TelemetryEndpointError("Telemetry protocol must be grpc or http")

    resolved = await resolve_telemetry_endpoint(otlp_endpoint)
    now = datetime.now(timezone.utc)
    config = await _get_config_record(db, owner_id=owner_id, for_update=True)
    if config is None:
        config = TelemetryBackendConfig(
            owner_id=owner_id,
            endpoint=resolved.endpoint,
            protocol=protocol,
            created_at=now,
            updated_at=now,
        )
        db.add(config)
    else:
        config.endpoint = resolved.endpoint
        config.protocol = protocol
        config.updated_at = now

    try:
        await db.commit()
    except IntegrityError:
        # A concurrent first write can win the unique owner row. Retry as an
        # update so tenant isolation remains database-enforced under races.
        await db.rollback()
        config = await _get_config_record(db, owner_id=owner_id, for_update=True)
        if config is None:
            raise
        config.endpoint = resolved.endpoint
        config.protocol = protocol
        config.updated_at = now
        await db.commit()

    await db.refresh(config)
    return _config_dict(config)


async def _connect_to_resolved_address(
    target: ResolvedTelemetryEndpoint,
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> None:
    ssl_context = ssl.create_default_context() if target.scheme == "https" else None
    _reader, writer = await asyncio.open_connection(
        host=str(address),
        port=target.port,
        ssl=ssl_context,
        server_hostname=target.hostname if ssl_context is not None else None,
    )
    writer.close()
    await writer.wait_closed()


async def _probe_endpoint(target: ResolvedTelemetryEndpoint) -> tuple[bool, str | None]:
    tasks = [
        asyncio.create_task(_connect_to_resolved_address(target, address))
        for address in target.addresses
    ]
    try:
        async with asyncio.timeout(CONNECT_TIMEOUT_SECONDS):
            for completed in asyncio.as_completed(tasks):
                try:
                    await completed
                except (OSError, ssl.SSLError):
                    continue
                return True, None
    except TimeoutError:
        return False, "connect_timeout"
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    return False, "connection_failed"


async def get_telemetry_health(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
) -> dict[str, Any]:
    """Safely check transport reachability for one tenant's saved target.

    DNS is repeated for every probe and the socket is opened to a validated IP,
    not the hostname. No HTTP client is involved, so proxy inheritance and
    redirect following are impossible.
    """
    config = await _get_config_record(db, owner_id=owner_id)
    if config is None:
        return {
            "configured": False,
            "endpoint_reachable": False,
            "using_grpc": False,
            "endpoint": None,
            "status": "unconfigured",
            "checked_at": None,
            "failure_reason": None,
        }

    checked_at = datetime.now(timezone.utc)
    try:
        target = await resolve_telemetry_endpoint(config.endpoint)
    except TelemetryEndpointError:
        return {
            "configured": True,
            "endpoint_reachable": False,
            "using_grpc": config.protocol == "grpc",
            "endpoint": config.endpoint,
            "status": "blocked",
            "checked_at": checked_at,
            "failure_reason": "unsafe_or_unresolvable_target",
        }

    reachable, failure_reason = await _probe_endpoint(target)
    return {
        "configured": True,
        "endpoint_reachable": reachable,
        "using_grpc": config.protocol == "grpc",
        "endpoint": config.endpoint,
        "status": "reachable" if reachable else "unreachable",
        "checked_at": checked_at,
        "failure_reason": failure_reason,
    }


async def is_telemetry_configured(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
) -> bool:
    return await _get_config_record(db, owner_id=owner_id) is not None


def get_runtime_telemetry_status() -> tuple[bool, str]:
    """Report the active process exporter without conflating it with saved state."""
    from src.api.telemetry import telemetry as runtime_telemetry

    provider = getattr(runtime_telemetry, "_tracer_provider", None)
    if provider is None:
        return False, "none"

    processor = getattr(provider, "_active_span_processor", None)
    processors = getattr(processor, "_span_processors", ())
    for span_processor in processors:
        exporter = getattr(span_processor, "span_exporter", None)
        if exporter is None:
            exporter = getattr(span_processor, "_span_exporter", None)
        if exporter is None:
            batch_processor = getattr(span_processor, "_batch_processor", None)
            exporter = getattr(batch_processor, "_exporter", None)
        exporter_name = exporter.__class__.__name__.lower() if exporter is not None else ""
        if "otlp" in exporter_name:
            return True, "otlp"
        if "zipkin" in exporter_name:
            return True, "zipkin"
        if "console" in exporter_name:
            return True, "console"

    requested_exporter = os.getenv("OTEL_TRACES_EXPORTER", "").strip().lower()
    if requested_exporter in {"otlp", "zipkin", "console"}:
        return True, requested_exporter
    return True, "unknown"
