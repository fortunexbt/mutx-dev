#!/usr/bin/env python3
"""Exercise MUTX's FPL and socket contracts against Faramesh v0.2.0."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import socket
import subprocess
import tempfile
import time
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "faramesh/faramesh-core"
VERSION = "0.2.0"
RELEASE_REF = "ae3ebc9066d65e4e930164881c2f2ce2be554c7f"
ASSET_SHA256 = {
    "darwin-amd64": "3febb4b39cb1cdad7dc1bec098394ef86711ff15510a5f5197fadb386c2c2020",
    "darwin-arm64": "6b89acce83e1b7dcbd3079f50c4762dc2657886413e3e3262d23f8d144a9ea24",
    "linux-amd64": "d95c739252957c1059e58a66d52b74262562ff7a8c43812e03e34755df650ed9",
    "linux-arm64": "316f92764546763c56840287cb1f94393637b93726e3b57cd552c6f009f57222",
}


def _platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    architecture = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(
        machine
    )
    if system not in {"darwin", "linux"} or architecture is None:
        raise RuntimeError(f"unsupported compatibility-runner platform: {system}/{machine}")
    return f"{system}-{architecture}"


def _download_binary(destination: Path) -> Path:
    platform_key = _platform_key()
    asset = f"faramesh-{platform_key}"
    url = f"https://github.com/{REPOSITORY}/releases/download/v{VERSION}/{asset}"
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - pinned host and digest
        destination.write_bytes(response.read())

    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    expected = ASSET_SHA256[platform_key]
    if digest != expected:
        raise RuntimeError(f"release asset digest mismatch: expected {expected}, got {digest}")
    destination.chmod(0o755)
    return destination


def _request(socket_path: Path, payload: dict) -> dict:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(2)
    try:
        client.connect(str(socket_path))
        client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        response = b""
        while b"\n" not in response:
            chunk = client.recv(4096)
            if not chunk:
                break
            response += chunk
    finally:
        client.close()
    if not response:
        raise RuntimeError(f"empty response for {payload['type']}")
    return json.loads(response.splitlines()[0])


def _load_policy(binary: Path, policy_path: Path, run_root: Path) -> None:
    policy_root = run_root / policy_path.stem
    policy_root.mkdir()
    socket_path = policy_root / "faramesh.sock"
    process = subprocess.Popen(
        [
            str(binary),
            "serve",
            "--policy",
            str(policy_path),
            "--socket",
            str(socket_path),
            "--data-dir",
            str(policy_root / "data"),
            "--log-level",
            "error",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and not socket_path.exists():
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                raise RuntimeError(
                    f"{policy_path.name} failed to load: {stderr.strip() or stdout.strip()}"
                )
            time.sleep(0.05)
        if not socket_path.exists():
            raise RuntimeError(f"{policy_path.name} did not expose its socket")

        status = _request(socket_path, {"type": "status"})
        if status.get("running") is not True or status.get("policy_loaded") is not True:
            raise RuntimeError(f"{policy_path.name} returned invalid status: {status}")

        if policy_path.name == "starter.fpl":
            decision = _request(
                socket_path,
                {
                    "type": "govern",
                    "call_id": "mutx-v020-compat",
                    "agent_id": "mutx-agent",
                    "session_id": "compat-session",
                    "tool_id": "api/read",
                    "args": {"resource": "health"},
                },
            )
            if decision.get("effect") != "PERMIT":
                raise RuntimeError(f"starter policy govern contract failed: {decision}")

            denied = _request(
                socket_path,
                {
                    "type": "govern",
                    "call_id": "mutx-v020-deny",
                    "agent_id": "mutx-agent",
                    "session_id": "compat-session",
                    "tool_id": "shell/run",
                    "args": {"cmd": "echo should-not-run"},
                },
            )
            if denied.get("effect") != "DENY":
                raise RuntimeError(f"starter deny contract failed: {denied}")

        if policy_path.name == "infra-bot.fpl":
            deferred = _request(
                socket_path,
                {
                    "type": "govern",
                    "call_id": "mutx-v020-defer",
                    "agent_id": "infra-bot",
                    "session_id": "compat-session",
                    "tool_id": "shell/run",
                    "args": {"cmd": "terraform plan"},
                },
            )
            defer_token = deferred.get("defer_token")
            if deferred.get("effect") != "DEFER" or not defer_token:
                raise RuntimeError(f"infra policy defer contract failed: {deferred}")

            pending = _request(socket_path, {"type": "agent", "op": "pending"})
            if not any(
                (item.get("defer_token") or item.get("token")) == defer_token
                for item in pending.get("items", [])
            ):
                raise RuntimeError(f"pending approval contract failed: {pending}")

            approved = _request(
                socket_path,
                {
                    "type": "approve_defer",
                    "defer_token": defer_token,
                    "approved": True,
                    "reason": "MUTX v0.2.0 compatibility test",
                },
            )
            if approved.get("ok") is not True:
                raise RuntimeError(f"approval contract failed: {approved}")

            resolved = _request(
                socket_path,
                {
                    "type": "poll_defer",
                    "agent_id": "infra-bot",
                    "defer_token": defer_token,
                },
            )
            if resolved.get("status") != "approved":
                raise RuntimeError(f"defer polling contract failed: {resolved}")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def run(binary: Path | None = None) -> None:
    # Darwin rejects Unix-domain socket paths longer than roughly 104 bytes.
    with tempfile.TemporaryDirectory(prefix="mfx-v020-", dir="/tmp") as temp_dir:
        run_root = Path(temp_dir)
        resolved_binary = binary or _download_binary(run_root / "faramesh")
        version = subprocess.run(
            [str(resolved_binary), "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        if version != VERSION:
            raise RuntimeError(f"expected Faramesh {VERSION}, got {version}")

        policies = sorted((ROOT / "cli" / "policies").glob("*.fpl"))
        if not policies:
            raise RuntimeError("no bundled FPL policies found")
        for policy in policies:
            _load_policy(resolved_binary, policy.resolve(), run_root)
            print(f"ok {policy.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, help="Use an already downloaded v0.2.0 binary")
    args = parser.parse_args()
    run(args.binary.resolve() if args.binary else None)


if __name__ == "__main__":
    main()
