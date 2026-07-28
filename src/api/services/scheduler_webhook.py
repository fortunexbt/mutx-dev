"""SSRF-resistant delivery for scheduler webhook actions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ipaddress
import re
import socket
from typing import Iterable
from urllib.parse import urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult

from src.api.models.scheduler_schemas import SchedulerWebhookPayload

WEBHOOK_TIMEOUT_SECONDS = 10
WEBHOOK_RETRY_BACKOFF_SECONDS = (0.25, 1.0, 2.0)

_NAT64_NETWORKS = (
    ipaddress.IPv6Network("64:ff9b::/96"),
    ipaddress.IPv6Network("64:ff9b:1::/48"),
)
_METADATA_ADDRESSES = frozenset(
    {
        ipaddress.ip_address("100.100.100.200"),
        ipaddress.ip_address("169.254.169.254"),
        ipaddress.ip_address("fd00:ec2::254"),
    }
)
_METADATA_HOSTNAMES = frozenset(
    {
        "instance-data",
        "instance-data.ec2.internal",
        "metadata.azure.internal",
        "metadata.google.internal",
        "metadata.goog",
    }
)
_NON_PUBLIC_HOST_SUFFIXES = (".internal", ".local", ".localhost", ".home.arpa")
_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_NUMERIC_HOST_COMPONENT = re.compile(r"^(?:0x[0-9a-f]+|[0-9]+)$", re.IGNORECASE)
_RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


class UnsafeSchedulerWebhookTarget(ValueError):
    """Raised when a scheduler webhook target is not unambiguously public."""


class SchedulerWebhookDeliveryError(RuntimeError):
    """Raised when a scheduler webhook request cannot be delivered safely."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class ResolvedSchedulerWebhookTarget:
    """A parsed webhook target and the only addresses its transport may connect to."""

    url: str
    hostname: str
    port: int
    addresses: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]


def _unsafe(message: str) -> UnsafeSchedulerWebhookTarget:
    return UnsafeSchedulerWebhookTarget(f"Unsafe scheduler webhook target: {message}")


def _assert_public_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    hostname: str,
) -> None:
    if address in _METADATA_ADDRESSES:
        raise _unsafe(f"'{hostname}' is a cloud metadata destination")

    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            raise _unsafe(f"'{hostname}' uses an IPv4-mapped IPv6 address")
        if any(address in network for network in _NAT64_NETWORKS):
            raise _unsafe(f"'{hostname}' uses a NAT64 address")
        if address.sixtofour is not None or address.teredo is not None:
            raise _unsafe(f"'{hostname}' uses an IPv4 transition address")

    if (
        not address.is_global
        or address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise _unsafe(f"'{hostname}' resolves to non-public address {address.compressed}")


def _normalize_hostname(
    raw_hostname: str,
) -> tuple[str, ipaddress.IPv4Address | ipaddress.IPv6Address | None]:
    if "%" in raw_hostname:
        raise _unsafe("percent-encoded or zone-qualified hostnames are not allowed")

    try:
        address = ipaddress.ip_address(raw_hostname)
    except ValueError:
        address = None

    if address is not None:
        return address.compressed, address

    try:
        hostname = raw_hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise _unsafe("hostname is malformed") from exc

    hostname = hostname.removesuffix(".")
    numeric_components = hostname.split(".")
    if numeric_components and all(
        _NUMERIC_HOST_COMPONENT.fullmatch(part) for part in numeric_components
    ):
        raise _unsafe("alternate numeric IP notation is not allowed")
    if "." not in hostname:
        raise _unsafe("single-label hostnames are not allowed")
    if len(hostname) > 253 or ".." in hostname:
        raise _unsafe("hostname is malformed")
    if any(not _DOMAIN_LABEL.fullmatch(label) for label in hostname.split(".")):
        raise _unsafe("hostname is malformed")
    if hostname == "localhost" or hostname.endswith(_NON_PUBLIC_HOST_SUFFIXES):
        raise _unsafe(f"'{hostname}' is not a public hostname")
    if hostname in _METADATA_HOSTNAMES:
        raise _unsafe(f"'{hostname}' is a cloud metadata destination")

    return hostname, None


def parse_scheduler_webhook_target(
    url: str,
) -> tuple[str, int, ipaddress.IPv4Address | ipaddress.IPv6Address | None]:
    """Parse a URL while rejecting ambiguous authority representations."""
    if not isinstance(url, str) or not url:
        raise _unsafe("URL is required")
    if any(ord(character) <= 0x20 or ord(character) == 0x7F for character in url):
        raise _unsafe("URL contains whitespace or control characters")
    if "\\" in url:
        raise _unsafe("backslashes are not allowed in URLs")
    if "#" in url:
        raise _unsafe("URL fragments are not allowed")

    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
        username = parsed.username
        password = parsed.password
    except ValueError as exc:
        raise _unsafe("URL authority is malformed") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise _unsafe("URL scheme must be http or https")
    if not parsed.netloc or hostname is None:
        raise _unsafe("URL must include a hostname")
    if username is not None or password is not None or "@" in parsed.netloc:
        raise _unsafe("URL credentials are not allowed")
    if parsed.netloc.endswith(":"):
        raise _unsafe("URL port is malformed")
    if port == 0:
        raise _unsafe("URL port must be between 1 and 65535")

    normalized_hostname, literal_address = _normalize_hostname(hostname)
    destination_port = port or (443 if parsed.scheme.lower() == "https" else 80)
    return normalized_hostname, destination_port, literal_address


async def resolve_scheduler_webhook_ips(hostname: str, port: int) -> tuple[str, ...]:
    """Resolve every TCP address for a hostname without retaining a DNS cache."""
    loop = asyncio.get_running_loop()
    try:
        addrinfo = await loop.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise _unsafe(f"'{hostname}' could not be resolved") from exc

    addresses = tuple(
        dict.fromkeys(sockaddr[0] for _, _, _, _, sockaddr in addrinfo if sockaddr and sockaddr[0])
    )
    if not addresses:
        raise _unsafe(f"'{hostname}' could not be resolved")
    return addresses


async def resolve_scheduler_webhook_target(url: str) -> ResolvedSchedulerWebhookTarget:
    """Resolve and validate every answer for one delivery or registration check."""
    hostname, port, literal_address = parse_scheduler_webhook_target(url)
    if literal_address is not None:
        addresses = (literal_address,)
    else:
        resolved = await resolve_scheduler_webhook_ips(hostname, port)
        parsed_addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        for value in resolved:
            if "%" in value:
                raise _unsafe(f"'{hostname}' resolved to a zone-qualified address")
            try:
                parsed_addresses.append(ipaddress.ip_address(value))
            except ValueError as exc:
                raise _unsafe(f"'{hostname}' returned a malformed DNS address") from exc
        addresses = tuple(dict.fromkeys(parsed_addresses))

    for address in addresses:
        _assert_public_address(address, hostname=hostname)

    return ResolvedSchedulerWebhookTarget(
        url=url,
        hostname=hostname,
        port=port,
        addresses=addresses,
    )


async def validate_scheduler_webhook_target(url: str) -> None:
    """Validate a scheduler webhook target at registration or update time."""
    await resolve_scheduler_webhook_target(url)


class _PinnedResolver(AbstractResolver):
    """Resolver that exposes only the addresses validated for this attempt."""

    def __init__(
        self,
        hostname: str,
        addresses: Iterable[ipaddress.IPv4Address | ipaddress.IPv6Address],
    ) -> None:
        self._hostname = hostname
        self._addresses = tuple(addresses)

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: socket.AddressFamily = socket.AF_INET,
    ) -> list[ResolveResult]:
        try:
            normalized_host, literal_address = _normalize_hostname(host)
        except UnsafeSchedulerWebhookTarget as exc:
            raise OSError(str(exc)) from exc
        if literal_address is not None or normalized_host != self._hostname:
            raise OSError("Refusing to resolve an unvalidated scheduler webhook hostname")

        results: list[ResolveResult] = []
        for address in self._addresses:
            address_family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
            if family not in {socket.AF_UNSPEC, address_family}:
                continue
            results.append(
                ResolveResult(
                    hostname=host,
                    host=address.compressed,
                    port=port,
                    family=address_family,
                    proto=socket.IPPROTO_TCP,
                    flags=0,
                )
            )
        return results

    async def close(self) -> None:
        return None


def _pinned_socket_factory(
    allowed_addresses: Iterable[ipaddress.IPv4Address | ipaddress.IPv6Address],
):
    allowed = frozenset(allowed_addresses)

    def create_socket(addr_info: tuple) -> socket.socket:
        family, sock_type, proto, _, sockaddr = addr_info
        try:
            address = ipaddress.ip_address(sockaddr[0])
        except ValueError as exc:
            raise OSError("Refusing malformed scheduler webhook connection address") from exc
        if address not in allowed:
            raise OSError("Refusing scheduler webhook connection to an unvalidated address")
        return socket.socket(family=family, type=sock_type, proto=proto)

    return create_socket


async def _send_pinned_webhook_request(
    target: ResolvedSchedulerWebhookTarget,
    payload: SchedulerWebhookPayload,
) -> int:
    resolver = _PinnedResolver(target.hostname, target.addresses)
    connector = aiohttp.TCPConnector(
        resolver=resolver,
        socket_factory=_pinned_socket_factory(target.addresses),
        use_dns_cache=False,
        force_close=True,
    )
    timeout = aiohttp.ClientTimeout(total=WEBHOOK_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
        trust_env=False,
    ) as session:
        async with session.request(
            payload.method,
            target.url,
            json=payload.body,
            headers=payload.headers,
            allow_redirects=False,
        ) as response:
            return response.status


async def _retry_wait(attempt: int) -> None:
    delay = WEBHOOK_RETRY_BACKOFF_SECONDS[min(attempt, len(WEBHOOK_RETRY_BACKOFF_SECONDS) - 1)]
    await asyncio.sleep(delay)


async def deliver_scheduler_webhook(payload: SchedulerWebhookPayload) -> int:
    """Deliver a webhook with fresh, transport-pinned DNS validation per attempt."""
    last_error: SchedulerWebhookDeliveryError | None = None

    for attempt in range(payload.max_retries + 1):
        target = await resolve_scheduler_webhook_target(payload.url)
        try:
            status = await _send_pinned_webhook_request(target, payload)
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            last_error = SchedulerWebhookDeliveryError(
                f"Webhook transport failed: {type(exc).__name__}",
                retryable=True,
            )
        else:
            if 200 <= status < 300:
                return status
            if 300 <= status < 400:
                raise SchedulerWebhookDeliveryError(
                    f"Webhook redirects are not followed (HTTP {status})"
                )
            last_error = SchedulerWebhookDeliveryError(
                f"Webhook returned HTTP {status}",
                retryable=status in _RETRYABLE_HTTP_STATUSES,
            )

        if not last_error.retryable or attempt >= payload.max_retries:
            raise last_error
        await _retry_wait(attempt)

    raise last_error or SchedulerWebhookDeliveryError("Webhook delivery failed")
