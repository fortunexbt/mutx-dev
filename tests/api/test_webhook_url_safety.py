import asyncio
from datetime import datetime, timedelta, timezone
import ipaddress
import socket
import ssl
import uuid

import aiohttp
import pytest
from aiohttp.abc import ResolveResult
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from httpx import AsyncClient
from sqlalchemy import select

from src.api.models.models import Webhook
from src.api.services import webhook_service
from src.api.services.webhook_service import (
    UnsafeWebhookDestinationError,
    ValidatedWebhookDestination,
    WebhookDestinationResolutionError,
    create_webhook_client_session,
    deliver_webhook,
    deliver_webhook_with_retry,
    ensure_safe_webhook_destination,
    resolve_webhook_destination_ips,
)


PUBLIC_IPV4 = "93.184.216.34"


@pytest.fixture(autouse=True)
def _public_dns_by_default(monkeypatch):
    async def resolve_public_destination(hostname: str, port: int) -> set[str]:
        assert port == 443
        return {PUBLIC_IPV4}

    monkeypatch.setattr(
        webhook_service,
        "resolve_webhook_destination_ips",
        resolve_public_destination,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/hook",
        "https://10.0.0.1/hook",
        "https://169.254.169.254/latest/meta-data",
        "https://169.254.170.2/v2/credentials",
        "https://100.100.100.200/latest/meta-data",
        "https://192.0.0.192/latest/meta-data",
        "https://224.0.0.1/hook",
        "https://192.0.2.1/hook",
        "https://192.0.0.9/hook",
        "https://192.88.99.1/hook",
        "https://0.0.0.0/hook",
        "https://[::1]/hook",
        "https://[fc00::1]/hook",
        "https://[fd00:ec2::254]/latest/meta-data",
        "https://[fe80::1]/hook",
        "https://[ff02::1]/hook",
        "https://[2001:db8::1]/hook",
        "https://[::]/hook",
        "https://[::ffff:127.0.0.1]/hook",
        "https://[64:ff9b::a9fe:a9fe]/hook",
        "https://[64:ff9b:1::a9fe:a9fe]/hook",
        "https://[2002:5db8:d822::]/hook",
        "https://[fec0::1]/hook",
        "https://[2606:4700:4700::1111]/hook",
        "https://[::ffff:5db8:d822]/hook",
    ],
)
async def test_validator_rejects_non_public_literal_addresses(url: str):
    with pytest.raises(UnsafeWebhookDestinationError, match="non-public address"):
        await ensure_safe_webhook_destination(url)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://2130706433/hook",
        "https://127.1/hook",
        "https://0177.0.0.1/hook",
        "https://0x7f000001/hook",
        "https://0x7f.0.0.1/hook",
        "https://127.0.0.01/hook",
    ],
)
async def test_validator_rejects_alternate_ipv4_encodings(url: str):
    with pytest.raises(UnsafeWebhookDestinationError, match="ambiguous or non-canonical"):
        await ensure_safe_webhook_destination(url)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("http://[64:ff9b::a9fe:a9fe]/", "must use HTTPS"),
        ("ftp://example.com/hook", "must use HTTPS"),
        ("gopher://example.com/hook", "must use HTTPS"),
        ("https://example.com:0/hook", "port 443"),
        ("https://example.com:22/hook", "port 443"),
        ("https://example.com:0443/hook", "canonical HTTPS representation"),
        ("https://user@example.com/hook", "user information"),
        ("https://user:password@example.com/hook", "user information"),
        ("https://exаmple.com/hook", "ASCII/IDNA"),
        ("https://example。com/hook", "ASCII/IDNA"),
        ("https://xn--e1awd7f.com/hook", "internationalized IDNA"),
        ("https://example.com./hook", "end with a dot"),
        ("https://example.com\\@127.0.0.1/hook", "backslashes"),
        ("https://example.com%2e/hook", "ambiguous encoding"),
        ("https://metadata.google.internal/hook", "non-public address"),
        ("https://example/hook", "fully qualified"),
        ("https://example.com/hook#internal", "fragment"),
        (" https://example.com/hook", "whitespace or control"),
    ],
)
async def test_validator_rejects_ambiguous_or_unsafe_urls(url: str, message: str):
    with pytest.raises(UnsafeWebhookDestinationError, match=message):
        await ensure_safe_webhook_destination(url)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resolved_ip",
    [
        "127.0.0.1",
        "10.0.0.9",
        "169.254.169.254",
        "224.0.0.1",
        "0.0.0.0",
        "::1",
        "fc00::1",
        "fe80::1",
        "ff02::1",
        "::ffff:127.0.0.1",
        "64:ff9b::a9fe:a9fe",
        "64:ff9b:1::a9fe:a9fe",
        "fec0::1",
        "2606:4700:4700::1111",
        "::ffff:93.184.216.34",
    ],
)
async def test_validator_rejects_non_public_dns_answers(monkeypatch, resolved_ip: str):
    async def resolve_unsafe_destination(hostname: str, port: int) -> set[str]:
        return {resolved_ip}

    monkeypatch.setattr(
        webhook_service,
        "resolve_webhook_destination_ips",
        resolve_unsafe_destination,
    )

    with pytest.raises(UnsafeWebhookDestinationError, match="non-public address"):
        await ensure_safe_webhook_destination("https://hooks.example.com/webhook")


@pytest.mark.asyncio
async def test_validator_rejects_mixed_public_and_private_dns_answers(monkeypatch):
    async def resolve_mixed_destination(hostname: str, port: int) -> set[str]:
        return {PUBLIC_IPV4, "10.0.0.9"}

    monkeypatch.setattr(
        webhook_service,
        "resolve_webhook_destination_ips",
        resolve_mixed_destination,
    )

    with pytest.raises(UnsafeWebhookDestinationError, match="non-public address"):
        await ensure_safe_webhook_destination("https://hooks.example.com/webhook")


@pytest.mark.asyncio
async def test_validator_preserves_original_https_url_and_all_public_answers(monkeypatch):
    async def resolve_public_destination(hostname: str, port: int) -> set[str]:
        assert hostname == "hooks.example.com"
        assert port == 443
        return {"1.1.1.1", PUBLIC_IPV4}

    monkeypatch.setattr(
        webhook_service,
        "resolve_webhook_destination_ips",
        resolve_public_destination,
    )

    destination = await ensure_safe_webhook_destination(
        "https://Hooks.Example.com:443/webhook?tenant=mutx"
    )

    assert destination.hostname == "hooks.example.com"
    assert destination.original_url == "https://Hooks.Example.com:443/webhook?tenant=mutx"
    assert destination.port == 443
    assert destination.resolved_ips == ("1.1.1.1", PUBLIC_IPV4)


@pytest.mark.asyncio
async def test_webhook_client_session_disables_pool_reuse_and_environment_proxies():
    destination = ValidatedWebhookDestination(
        original_url="https://hooks.example.com/webhook",
        hostname="hooks.example.com",
        port=443,
        addresses=(ipaddress.IPv4Address(PUBLIC_IPV4),),
    )

    async with create_webhook_client_session(destination) as session:
        assert session.connector is not None
        assert session.connector.force_close is True
        assert session.connector.use_dns_cache is False
        assert session.trust_env is False


def test_socket_factory_rejects_any_address_outside_the_validated_set():
    factory = webhook_service._pinned_webhook_socket_factory(
        (ipaddress.IPv4Address(PUBLIC_IPV4),),
        443,
    )

    with pytest.raises(OSError, match="unvalidated address"):
        factory(
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("1.1.1.1", 443),
            )
        )

    with pytest.raises(OSError, match="unvalidated address"):
        factory(
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (PUBLIC_IPV4, 444),
            )
        )


def _webhook(url: str = "https://hooks.example.com/webhook") -> Webhook:
    return Webhook(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        url=url,
        events=["*"],
        secret=None,
        is_active=True,
    )


@pytest.mark.asyncio
async def test_delivery_uses_original_url_with_the_validated_address_set(monkeypatch):
    sent: list[ValidatedWebhookDestination] = []

    async def record_transport(destination, payload_json, headers, **kwargs):
        sent.append(destination)
        return 204, ""

    monkeypatch.setattr(webhook_service, "_send_pinned_webhook_request", record_transport)

    result = await deliver_webhook(
        _webhook(),
        "agent.status",
        {"new_status": "running"},
        uuid.uuid4(),
    )

    assert result[0] is True
    assert result[1] == 204
    assert len(sent) == 1
    assert sent[0].original_url == "https://hooks.example.com/webhook"
    assert sent[0].resolved_ips == (PUBLIC_IPV4,)


@pytest.mark.asyncio
async def test_delivery_does_not_retry_or_follow_redirect_to_private_target(monkeypatch):
    calls = 0

    async def redirect_response(destination, payload_json, headers, **kwargs):
        nonlocal calls
        calls += 1
        return 302, "redirect refused"

    monkeypatch.setattr(webhook_service, "_send_pinned_webhook_request", redirect_response)

    success, status_code, error_message, _, _ = await deliver_webhook(
        _webhook(),
        "test",
        {},
        uuid.uuid4(),
    )

    assert success is False
    assert status_code == 302
    assert error_message == "HTTP 302: redirect refused"
    assert calls == 1


def _local_tls_contexts(tmp_path) -> tuple[ssl.SSLContext, ssl.SSLContext]:
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "MUTX webhook test CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "hooks.example.com")])
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(server_name)
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("hooks.example.com")]),
            critical=False,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    ca_path = tmp_path / "ca.pem"
    cert_path = tmp_path / "server.pem"
    key_path = tmp_path / "server-key.pem"
    ca_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    cert_path.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )

    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert_path, key_path)
    client_context = ssl.create_default_context(cafile=str(ca_path))
    return server_context, client_context


@pytest.mark.asyncio
async def test_real_pinned_tls_connector_preserves_host_sni_and_cannot_escape(
    tmp_path,
    monkeypatch,
):
    server_context, client_context = _local_tls_contexts(tmp_path)
    seen_sni: list[str | None] = []
    requests: list[str] = []

    def record_sni(ssl_socket, server_name, ssl_context):
        seen_sni.append(server_name)

    server_context.set_servername_callback(record_sni)

    async def handle_request(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = await reader.readuntil(b"\r\n\r\n")
        requests.append(request.decode("ascii"))
        writer.write(b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    try:
        server = await asyncio.start_server(
            handle_request,
            "127.0.0.1",
            0,
            ssl=server_context,
        )
    except PermissionError:
        pytest.skip("sandbox does not permit binding a loopback TLS integration server")
    port = server.sockets[0].getsockname()[1]
    address = ipaddress.IPv4Address("127.0.0.1")
    destination = ValidatedWebhookDestination(
        original_url=f"https://hooks.example.com:{port}/webhook?source=integration",
        hostname="hooks.example.com",
        port=port,
        addresses=(address,),
    )

    try:
        status, _ = await webhook_service._send_pinned_webhook_request(
            destination,
            "{}",
            {"Content-Type": "application/json"},
            ssl_context=client_context,
        )
        assert status == 204
        assert seen_sni == ["hooks.example.com"]
        assert len(requests) == 1
        assert requests[0].startswith("POST /webhook?source=integration HTTP/1.1\r\n")
        assert f"\r\nHost: hooks.example.com:{port}\r\n" in requests[0]

        wrong_hostname = ValidatedWebhookDestination(
            original_url=f"https://wrong.example.com:{port}/webhook",
            hostname="wrong.example.com",
            port=port,
            addresses=(address,),
        )
        with pytest.raises(aiohttp.ClientConnectorCertificateError):
            await webhook_service._send_pinned_webhook_request(
                wrong_hostname,
                "{}",
                {"Content-Type": "application/json"},
                ssl_context=client_context,
            )

        async with create_webhook_client_session(
            destination,
            ssl_context=client_context,
        ) as session:
            resolver = session.connector._resolver

            async def escape_resolution(host, port=0, family=socket.AF_INET):
                return [
                    ResolveResult(
                        hostname=host,
                        host="127.0.0.2",
                        port=port,
                        family=socket.AF_INET,
                        proto=socket.IPPROTO_TCP,
                        flags=0,
                    )
                ]

            monkeypatch.setattr(resolver, "resolve", escape_resolution)
            with pytest.raises(aiohttp.ClientConnectorError) as escape_error:
                await session.get(destination.original_url)
            assert "unvalidated address" in str(escape_error.value.__cause__)
            assert len(requests) == 1
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_retry_revalidates_dns_and_blocks_rebinding(
    client: AsyncClient,
    db_session,
    test_user,
    monkeypatch,
):
    test_user.roles = ["DEVELOPER"]
    await db_session.commit()
    create_response = await client.post(
        "/v1/webhooks/",
        json={"url": "https://hooks.example.com/webhook", "events": ["*"]},
    )
    assert create_response.status_code == 201
    webhook_id = uuid.UUID(create_response.json()["id"])
    webhook = (
        await db_session.execute(select(Webhook).where(Webhook.id == webhook_id))
    ).scalar_one()

    answers = iter(({PUBLIC_IPV4}, {"169.254.169.254"}))
    resolution_count = 0

    async def resolve_rebinding_destination(hostname: str, port: int) -> set[str]:
        nonlocal resolution_count
        resolution_count += 1
        return next(answers)

    async def no_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr(
        webhook_service,
        "resolve_webhook_destination_ips",
        resolve_rebinding_destination,
    )
    monkeypatch.setattr(webhook_service, "MAX_RETRIES", 2)
    monkeypatch.setattr(webhook_service.asyncio, "sleep", no_sleep)
    send_count = 0

    async def retryable_response(destination, payload_json, headers, **kwargs):
        nonlocal send_count
        send_count += 1
        return 500, "try again"

    monkeypatch.setattr(
        webhook_service,
        "_send_pinned_webhook_request",
        retryable_response,
    )

    success = await deliver_webhook_with_retry(
        db_session,
        webhook,
        "test",
        {"message": "revalidate me"},
    )

    assert success is False
    assert resolution_count == 2
    assert send_count == 1


@pytest.mark.asyncio
async def test_dns_resolution_timeout_is_bounded_and_retryable(monkeypatch):
    loop = asyncio.get_running_loop()

    async def never_resolves(self, *args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(type(loop), "getaddrinfo", never_resolves)
    monkeypatch.setattr(webhook_service, "DNS_RESOLUTION_TIMEOUT_SECONDS", 0.01)

    with pytest.raises(WebhookDestinationResolutionError, match="timed out") as error:
        await resolve_webhook_destination_ips("hooks.example.com", 443)

    assert error.value.retryable is True


@pytest.mark.asyncio
async def test_transient_resolution_failure_is_freshly_retried(
    db_session,
    test_user,
    monkeypatch,
):
    webhook = _webhook()
    webhook.user_id = test_user.id
    db_session.add(webhook)
    await db_session.commit()

    resolution_count = 0
    send_count = 0

    async def transient_then_public(hostname: str, port: int):
        nonlocal resolution_count
        resolution_count += 1
        if resolution_count == 1:
            raise WebhookDestinationResolutionError(
                "temporary DNS failure",
                retryable=True,
            )
        return (PUBLIC_IPV4,)

    async def successful_transport(destination, payload_json, headers, **kwargs):
        nonlocal send_count
        send_count += 1
        return 204, ""

    async def no_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr(
        webhook_service,
        "resolve_webhook_destination_ips",
        transient_then_public,
    )
    monkeypatch.setattr(
        webhook_service,
        "_send_pinned_webhook_request",
        successful_transport,
    )
    monkeypatch.setattr(webhook_service, "MAX_RETRIES", 2)
    monkeypatch.setattr(webhook_service.asyncio, "sleep", no_sleep)

    assert await deliver_webhook_with_retry(db_session, webhook, "test", {}) is True
    assert resolution_count == 2
    assert send_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("http://example.com/hook", "must use HTTPS"),
        ("https://127.0.0.1/hook", "non-public address"),
        ("https://[64:ff9b::a9fe:a9fe]/", "non-public address"),
        ("https://user@example.com/hook", "user information"),
        ("https://example.com:22/hook", "port 443"),
    ],
)
async def test_create_route_returns_actionable_400_for_unsafe_url(
    client: AsyncClient,
    db_session,
    test_user,
    url: str,
    message: str,
):
    test_user.roles = ["DEVELOPER"]
    await db_session.commit()
    response = await client.post(
        "/v1/webhooks/",
        json={"url": url, "events": ["*"]},
    )

    assert response.status_code == 400
    assert message in response.json()["detail"]
