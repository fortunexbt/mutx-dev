from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.services.faramesh_supervisor import (
    FarameshSupervisor,
    SupervisionConfig,
    SupervisionValidationError,
)


def test_supervisor_rejects_launch_when_command_allowlist_is_unset():
    supervisor = FarameshSupervisor(SupervisionConfig())

    with pytest.raises(
        SupervisionValidationError,
        match="GOVERNANCE_SUPERVISED_COMMAND_ALLOWLIST",
    ):
        supervisor.sanitize_launch_request("agent-1", ["python", "agent.py"])


def test_supervisor_rejects_disallowed_environment_variables():
    supervisor = FarameshSupervisor(
        SupervisionConfig(
            allowed_commands=("python",),
            allowed_env_keys=("LOG_LEVEL",),
        )
    )

    with pytest.raises(SupervisionValidationError, match="SECRET_KEY"):
        supervisor.sanitize_launch_request(
            "agent-1",
            ["python", "agent.py"],
            {"SECRET_KEY": "top-secret"},
        )


def test_supervisor_resolves_named_launch_profile_without_direct_command_access():
    supervisor = FarameshSupervisor(
        SupervisionConfig(
            profiles={
                "assistant-runner": {
                    "command": ["python", "agent.py"],
                    "env": {"LOG_LEVEL": "info", "MODE": "prod"},
                }
            },
            allowed_env_keys=("LOG_LEVEL",),
        )
    )

    prepared = supervisor.prepare_launch_request(
        "agent-1",
        profile_name="assistant-runner",
        env={"LOG_LEVEL": "debug"},
    )

    assert prepared.agent_id == "agent-1"
    assert prepared.command == ["python", "agent.py"]
    assert prepared.env == {"LOG_LEVEL": "debug", "MODE": "prod"}
    assert prepared.launch_profile == "assistant-runner"


def test_supervisor_rejects_direct_launch_when_profile_mode_is_enabled():
    supervisor = FarameshSupervisor(
        SupervisionConfig(
            allowed_commands=("python",),
            allowed_env_keys=("LOG_LEVEL",),
            allow_direct_commands=False,
        )
    )

    with pytest.raises(SupervisionValidationError, match="launch profile"):
        supervisor.prepare_launch_request(
            "agent-1",
            command=["python", "agent.py"],
        )


def test_supervisor_rejects_per_launch_policy_override(tmp_path: Path):
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir()
    policy_file = policy_dir / "agent.fpl"
    policy_file.write_text("allow test\n")

    supervisor = FarameshSupervisor(
        SupervisionConfig(
            allowed_commands=("python",),
            allowed_env_keys=("LOG_LEVEL",),
            allowed_policy_dir=str(policy_dir),
        )
    )

    with pytest.raises(SupervisionValidationError, match="governance.fms"):
        supervisor.sanitize_launch_request(
            " agent-1 ",
            ["/usr/bin/python", "agent.py"],
            {"LOG_LEVEL": "debug"},
            "agent.fpl",
        )


@pytest.mark.asyncio
async def test_supervisor_uses_apply_generated_launcher_and_official_socket_env(
    tmp_path: Path,
):
    launcher = tmp_path / ".faramesh" / "bin" / "agent"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\nexec \"$@\"\n")
    launcher.chmod(0o755)
    supervisor = FarameshSupervisor(
        SupervisionConfig(
            agent_launcher=str(launcher),
            socket_path="/tmp/faramesh.sock",
            allowed_commands=("python",),
            allowed_env_keys=("LOG_LEVEL",),
            allow_direct_commands=True,
        )
    )
    prepared = supervisor.prepare_launch_request(
        "agent-1",
        command=["python", "agent.py"],
        env={"LOG_LEVEL": "debug"},
    )
    process = MagicMock(pid=42)
    process.poll.return_value = None

    with (
        patch(
            "src.api.services.faramesh_supervisor.subprocess.Popen",
            return_value=process,
        ) as popen,
        patch(
            "src.api.services.faramesh_supervisor.asyncio.sleep",
            new=AsyncMock(),
        ),
    ):
        started = await supervisor.start_prepared_agent(prepared)

    assert started is True
    assert popen.call_args.args[0] == [str(launcher.resolve()), "python", "agent.py"]
    launch_env = popen.call_args.kwargs["env"]
    assert launch_env["FAREMESH_SOCKET"] == "/tmp/faramesh.sock"
    assert launch_env["FAREMESH_SOCKET_PATH"] == "/tmp/faramesh.sock"
    assert launch_env["LOG_LEVEL"] == "debug"
