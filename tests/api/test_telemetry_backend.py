"""Adversarial tests for telemetry backend persistence and SSRF defenses."""

from __future__ import annotations

import asyncio
import ipaddress
import socket

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import src.api.services.telemetry_backend as telemetry_backend
from src.api.models.telemetry_backend import TelemetryBackendConfig


def _endpoint_for(address: str) -> str:
    host = f"[{address}]" if ":" in address else address
    return f"http://{host}:4317"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "address",
    [
        "0.0.0.0",
        "10.0.0.1",
        "100.64.0.1",
        "127.0.0.1",
        "169.254.169.254",
        "172.16.0.1",
        "192.0.2.1",
        "192.168.0.1",
        "224.0.0.1",
        "::1",
        "fc00::1",
        "fe80::1",
        "fec0::1",
        "ff02::1",
        "2001:db8::1",
        "::ffff:8.8.8.8",
        "64:ff9b::808:808",
        "64:ff9b:1::808:808",
        "2002:0808:0808::1",
        "2001:0000:4136:e378:8000:63bf:3fff:fdd2",
    ],
)
async def test_rejects_private_reserved_link_local_site_local_and_transition_addresses(
    address: str,
):
    with pytest.raises(telemetry_backend.TelemetryEndpointError):
        await telemetry_backend.resolve_telemetry_endpoint(_endpoint_for(address))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint",
    [
        "file:///tmp/collector",
        "ftp://collector.example:4317",
        "http://user:password@collector.example:4317",
        "http://collector.example:4317?next=http://169.254.169.254",
        "http://collector.example:4317/#fragment",
        "http://[fe80::1%25eth0]:4317",
        "http://collector.example:99999",
    ],
)
async def test_rejects_ambiguous_or_dangerous_url_forms(endpoint: str):
    with pytest.raises(telemetry_backend.TelemetryEndpointError):
        await telemetry_backend.resolve_telemetry_endpoint(endpoint)


@pytest.mark.asyncio
async def test_rejects_dns_answer_if_any_address_is_non_public(
    monkeypatch: pytest.MonkeyPatch,
):
    async def mixed_dns(_hostname: str, port: int):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("8.8.8.8", port)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.8", port)),
        ]

    monkeypatch.setattr(telemetry_backend, "_getaddrinfo", mixed_dns)

    with pytest.raises(
        telemetry_backend.TelemetryEndpointError,
        match="non-public",
    ):
        await telemetry_backend.resolve_telemetry_endpoint("https://collector.example:4317")


@pytest.mark.asyncio
async def test_dns_lookup_has_a_hard_deadline(monkeypatch: pytest.MonkeyPatch):
    async def hanging_dns(_hostname: str, _port: int):
        await asyncio.Event().wait()

    monkeypatch.setattr(telemetry_backend, "_getaddrinfo", hanging_dns)
    monkeypatch.setattr(telemetry_backend, "DNS_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(telemetry_backend.TelemetryEndpointError, match="timed out"):
        await telemetry_backend.resolve_telemetry_endpoint("https://collector.example:4317")


@pytest.mark.asyncio
async def test_excessive_dns_answers_are_rejected(monkeypatch: pytest.MonkeyPatch):
    async def excessive_dns(_hostname: str, port: int):
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (f"8.8.8.{suffix}", port),
            )
            for suffix in range(1, telemetry_backend.MAX_RESOLVED_ADDRESSES + 2)
        ]

    monkeypatch.setattr(telemetry_backend, "_getaddrinfo", excessive_dns)

    with pytest.raises(telemetry_backend.TelemetryEndpointError, match="too many"):
        await telemetry_backend.resolve_telemetry_endpoint("https://collector.example:4317")


@pytest.mark.asyncio
async def test_health_reresolves_and_blocks_dns_rebinding_before_connect(
    db_session,
    test_user,
    monkeypatch: pytest.MonkeyPatch,
):
    answers = iter(["8.8.8.8", "10.0.0.7"])

    async def rebinding_dns(_hostname: str, port: int):
        address = next(answers)
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, port))]

    connect_called = False

    async def must_not_connect(_target):
        nonlocal connect_called
        connect_called = True
        return True, None

    monkeypatch.setattr(telemetry_backend, "_getaddrinfo", rebinding_dns)
    monkeypatch.setattr(telemetry_backend, "_probe_endpoint", must_not_connect)

    await telemetry_backend.configure_telemetry_backend(
        db_session,
        owner_id=test_user.id,
        otlp_endpoint="http://collector.example:4317",
        protocol="grpc",
    )
    health = await telemetry_backend.get_telemetry_health(
        db_session,
        owner_id=test_user.id,
    )

    assert health["status"] == "blocked"
    assert health["failure_reason"] == "unsafe_or_unresolvable_target"
    assert connect_called is False


@pytest.mark.asyncio
async def test_probe_ignores_proxies_redirect_paths_and_pins_the_validated_ip(
    db_session,
    test_user,
    monkeypatch: pytest.MonkeyPatch,
):
    db_session.add(
        TelemetryBackendConfig(
            owner_id=test_user.id,
            endpoint="http://collector.example:4317/redirect",
            protocol="http",
        )
    )
    await db_session.commit()

    target = telemetry_backend.ResolvedTelemetryEndpoint(
        endpoint="http://collector.example:4317/redirect",
        scheme="http",
        hostname="collector.example",
        port=4317,
        addresses=(ipaddress.ip_address("8.8.8.8"),),
    )

    async def resolved(_endpoint: str):
        return target

    connected: list[tuple[str, int]] = []

    class FakeWriter:
        def close(self) -> None:
            return None

        async def wait_closed(self) -> None:
            return None

    async def open_connection(*, host, port, ssl, server_hostname):
        connected.append((host, port))
        assert ssl is None
        assert server_hostname is None
        return object(), FakeWriter()

    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:8888")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:8888")
    monkeypatch.setattr(telemetry_backend, "resolve_telemetry_endpoint", resolved)
    monkeypatch.setattr(asyncio, "open_connection", open_connection)

    health = await telemetry_backend.get_telemetry_health(
        db_session,
        owner_id=test_user.id,
    )

    assert health["status"] == "reachable"
    assert connected == [("8.8.8.8", 4317)]


@pytest.mark.asyncio
async def test_connect_probe_has_one_overall_deadline(
    db_session,
    test_user,
    monkeypatch: pytest.MonkeyPatch,
):
    db_session.add(
        TelemetryBackendConfig(
            owner_id=test_user.id,
            endpoint="http://8.8.8.8:4317",
            protocol="grpc",
        )
    )
    await db_session.commit()

    async def hanging_connect(_target, _address):
        await asyncio.Event().wait()

    monkeypatch.setattr(telemetry_backend, "_connect_to_resolved_address", hanging_connect)
    monkeypatch.setattr(telemetry_backend, "CONNECT_TIMEOUT_SECONDS", 0.01)

    health = await telemetry_backend.get_telemetry_health(
        db_session,
        owner_id=test_user.id,
    )

    assert health["status"] == "unreachable"
    assert health["failure_reason"] == "connect_timeout"


def test_runtime_status_reports_the_installed_batch_processor_exporter(
    monkeypatch: pytest.MonkeyPatch,
):
    from src.api.telemetry import telemetry as runtime_telemetry

    class OTLPSpanExporter:
        pass

    class BatchProcessor:
        _exporter = OTLPSpanExporter()

    class SpanProcessor:
        _batch_processor = BatchProcessor()

    class ActiveProcessor:
        _span_processors = (SpanProcessor(),)

    class Provider:
        _active_span_processor = ActiveProcessor()

    monkeypatch.setattr(runtime_telemetry, "_tracer_provider", Provider())

    assert telemetry_backend.get_runtime_telemetry_status() == (True, "otlp")


@pytest.mark.asyncio
async def test_configuration_survives_a_fresh_service_session(
    test_engine,
    test_user,
):
    session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as first_process_session:
        await telemetry_backend.configure_telemetry_backend(
            first_process_session,
            owner_id=test_user.id,
            otlp_endpoint="http://8.8.8.8:4317",
            protocol="grpc",
        )

    # A new database session is the persistence boundary used by a restarted
    # API worker. There are no module globals to seed the second service call.
    assert not hasattr(telemetry_backend, "_otlp_endpoint")
    assert not hasattr(telemetry_backend, "_configured")
    async with session_factory() as restarted_process_session:
        config = await telemetry_backend.get_current_config(
            restarted_process_session,
            owner_id=test_user.id,
        )

    assert config["configured"] is True
    assert config["endpoint"] == "http://8.8.8.8:4317"
    assert config["protocol"] == "grpc"
