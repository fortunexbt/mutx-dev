from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


ROOT = Path(__file__).resolve().parents[3]
VERIFIER = ROOT / "scripts" / "verify-production-tls.sh"
HOSTS = ("mutx.dev", "www.mutx.dev", "app.mutx.dev", "pico.mutx.dev", "api.mutx.dev")


def create_ca(common_name: str) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return key, certificate


def create_leaf(
    ca_key: rsa.RSAPrivateKey,
    ca_certificate: x509.Certificate,
    *,
    hosts: tuple[str, ...] = HOSTS,
    not_before: datetime | None = None,
    not_after: datetime | None = None,
) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hosts[0])]))
        .issuer_name(ca_certificate.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before or now - timedelta(hours=1))
        .not_valid_after(not_after or now + timedelta(days=30))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(host) for host in hosts]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    return key, certificate


def write_material(
    directory: Path,
    *,
    hosts: tuple[str, ...] = HOSTS,
    not_before: datetime | None = None,
    not_after: datetime | None = None,
    trusted_ca: x509.Certificate | None = None,
    private_key_override: rsa.RSAPrivateKey | None = None,
) -> tuple[Path, Path, Path, Path]:
    ca_key, ca_certificate = create_ca("MUTX release test CA")
    leaf_key, leaf_certificate = create_leaf(
        ca_key,
        ca_certificate,
        hosts=hosts,
        not_before=not_before,
        not_after=not_after,
    )

    certificate_file = directory / "cert.pem"
    private_key_file = directory / "key.pem"
    ca_file = directory / "ca.pem"
    nginx_config = directory / "nginx.conf"
    certificate_file.write_bytes(leaf_certificate.public_bytes(serialization.Encoding.PEM))
    private_key_file.write_bytes(
        (private_key_override or leaf_key).private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    ca_file.write_bytes((trusted_ca or ca_certificate).public_bytes(serialization.Encoding.PEM))
    nginx_config.write_text(
        """
http {
    ssl_protocols TLSv1.2 TLSv1.3;
    server {
        listen 443 ssl;
        server_name mutx.dev www.mutx.dev app.mutx.dev pico.mutx.dev;
    }
    server {
        listen 443 ssl;
        server_name api.mutx.dev;
    }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return certificate_file, private_key_file, ca_file, nginx_config


def run_verifier(material: tuple[Path, Path, Path, Path]) -> subprocess.CompletedProcess[str]:
    certificate_file, private_key_file, ca_file, nginx_config = material
    return subprocess.run(
        [
            "bash",
            str(VERIFIER),
            str(certificate_file),
            str(private_key_file),
            str(nginx_config),
            str(ca_file),
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )


def test_tls_preflight_accepts_a_trusted_current_certificate_for_every_host(
    tmp_path: Path,
) -> None:
    result = run_verifier(write_material(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "chain trust verified" in result.stdout


def test_tls_preflight_rejects_missing_hostname_coverage(tmp_path: Path) -> None:
    result = run_verifier(
        write_material(
            tmp_path,
            hosts=("mutx.dev", "www.mutx.dev", "app.mutx.dev", "pico.mutx.dev"),
        )
    )

    assert result.returncode != 0
    assert "api.mutx.dev" in result.stderr


def test_tls_preflight_rejects_missing_pico_hostname_coverage(tmp_path: Path) -> None:
    result = run_verifier(
        write_material(
            tmp_path,
            hosts=("mutx.dev", "www.mutx.dev", "app.mutx.dev", "api.mutx.dev"),
        )
    )

    assert result.returncode != 0
    assert "pico.mutx.dev" in result.stderr


def test_tls_preflight_rejects_a_certificate_that_is_not_valid_yet(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    result = run_verifier(
        write_material(
            tmp_path,
            not_before=now + timedelta(days=1),
            not_after=now + timedelta(days=31),
        )
    )

    assert result.returncode != 0
    assert "not valid yet" in result.stderr


def test_tls_preflight_rejects_expiry_inside_the_safety_buffer(tmp_path: Path) -> None:
    result = run_verifier(
        write_material(tmp_path, not_after=datetime.now(timezone.utc) + timedelta(days=7))
    )

    assert result.returncode != 0
    assert "14-day safety buffer" in result.stderr


def test_tls_preflight_rejects_an_untrusted_chain(tmp_path: Path) -> None:
    _, unrelated_ca = create_ca("Unrelated CA")
    result = run_verifier(write_material(tmp_path, trusted_ca=unrelated_ca))

    assert result.returncode != 0
    assert "chain is not trusted" in result.stderr


def test_tls_preflight_rejects_a_mismatched_private_key(tmp_path: Path) -> None:
    unrelated_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    result = run_verifier(write_material(tmp_path, private_key_override=unrelated_key))

    assert result.returncode != 0
    assert "private key do not match" in result.stderr
