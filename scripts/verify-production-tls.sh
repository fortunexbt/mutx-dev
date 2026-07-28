#!/usr/bin/env bash

set -euo pipefail

certificate_file="${1:-}"
private_key_file="${2:-}"
nginx_config="${3:-}"
ca_file="${4:-}"
minimum_validity_seconds=1209600

for command_name in openssl python3 awk sort cmp mktemp; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Required TLS verification command is unavailable: ${command_name}" >&2
    exit 1
  fi
done

for required_file in "${certificate_file}" "${private_key_file}" "${nginx_config}"; do
  if [[ -z "${required_file}" || ! -f "${required_file}" ]]; then
    echo "TLS verification input is missing: ${required_file:-<empty>}" >&2
    exit 1
  fi
done

if ! grep -Eq 'ssl_protocols[[:space:]]+TLSv1\.2 TLSv1\.3;' "${nginx_config}"; then
  echo "nginx production config must allow exactly TLS 1.2 and TLS 1.3." >&2
  exit 1
fi

configured_hosts=()
while IFS= read -r host; do
  configured_hosts+=("${host}")
done < <(
  awk '
    /^[[:space:]]*server_name[[:space:]]+/ {
      for (field_index = 2; field_index <= NF; field_index += 1) {
        host = $field_index
        sub(/;$/, "", host)
        if (host != "_") print host
      }
    }
  ' "${nginx_config}" | LC_ALL=C sort -u
)

if [[ "${#configured_hosts[@]}" -eq 0 ]]; then
  echo "No concrete TLS hosts are configured in ${nginx_config}." >&2
  exit 1
fi
for host in "${configured_hosts[@]}"; do
  if [[ ! "${host}" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]]; then
    echo "Cannot fail-closed verify non-concrete nginx TLS host: ${host}" >&2
    exit 1
  fi
done

temporary_directory="$(mktemp -d "${TMPDIR:-/tmp}/mutx-tls-verify.XXXXXX")"
leaf_file="${temporary_directory}/leaf.pem"
chain_file="${temporary_directory}/chain.pem"

cleanup() {
  rm -f "${leaf_file}" "${chain_file}"
  rmdir "${temporary_directory}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

python3 - "${certificate_file}" "${leaf_file}" "${chain_file}" <<'PY'
import re
import sys
from pathlib import Path

source, leaf_path, chain_path = map(Path, sys.argv[1:])
blocks = re.findall(
    rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----\s*",
    source.read_bytes(),
    flags=re.DOTALL,
)
if not blocks:
    raise SystemExit("cert.pem does not contain a PEM certificate")
leaf_path.write_bytes(blocks[0])
chain_path.write_bytes(b"".join(blocks[1:]))
PY

openssl x509 -in "${leaf_file}" -noout >/dev/null
openssl pkey -in "${private_key_file}" -noout -check >/dev/null
if ! cmp -s \
  <(openssl x509 -in "${leaf_file}" -pubkey -noout) \
  <(openssl pkey -in "${private_key_file}" -pubout); then
  echo "TLS certificate and private key do not match." >&2
  exit 1
fi

if ! openssl x509 -in "${leaf_file}" -noout -checkend "${minimum_validity_seconds}" >/dev/null; then
  echo "TLS certificate expires inside the mandatory 14-day safety buffer." >&2
  exit 1
fi

python3 - "${leaf_file}" <<'PY'
import subprocess
import sys
from datetime import datetime, timezone

output = subprocess.check_output(
    ["openssl", "x509", "-in", sys.argv[1], "-noout", "-startdate"],
    text=True,
).strip()
try:
    not_before = datetime.strptime(output.split("=", 1)[1], "%b %d %H:%M:%S %Y %Z")
except (IndexError, ValueError) as error:
    raise SystemExit(f"Could not parse certificate notBefore: {output}") from error
if not_before.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
    raise SystemExit("TLS certificate is not valid yet")
PY

verify_trust_args=()
if [[ -n "${ca_file}" ]]; then
  if [[ ! -f "${ca_file}" ]]; then
    echo "Configured CA file does not exist: ${ca_file}" >&2
    exit 1
  fi
  verify_trust_args+=( -CAfile "${ca_file}" )
fi
if [[ -s "${chain_file}" ]]; then
  verify_trust_args+=( -untrusted "${chain_file}" )
fi

for host in "${configured_hosts[@]}"; do
  if ! openssl x509 -in "${leaf_file}" -noout -checkhost "${host}" >/dev/null; then
    echo "TLS certificate does not cover configured nginx host: ${host}" >&2
    exit 1
  fi
  if ! openssl verify -purpose sslserver -verify_hostname "${host}" \
    "${verify_trust_args[@]}" "${leaf_file}" >/dev/null; then
    echo "TLS chain is not trusted for configured nginx host: ${host}" >&2
    exit 1
  fi
done

echo "TLS certificate, key, validity window, host coverage, and chain trust verified."
