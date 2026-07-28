from subprocess import CompletedProcess
from typing import Any

import pytest

from cli import desktop_bridge


def test_native_actions_are_registered_under_the_canonical_methods() -> None:
    assert desktop_bridge.METHODS["finder.reveal"] is desktop_bridge.finder_reveal
    assert desktop_bridge.METHODS["shell.openTerminal"] is desktop_bridge.shell_open_terminal
    assert "system.revealInFinder" not in desktop_bridge.METHODS
    assert "system.openTerminal" not in desktop_bridge.METHODS


def test_finder_reveal_uses_an_argument_vector(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "artifact; touch not-executed"
    target.write_text("artifact")
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        calls.append((command, kwargs))
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(desktop_bridge.subprocess, "run", fake_run)

    assert desktop_bridge.finder_reveal(str(target)) == {"success": True}
    assert calls == [
        (
            ["open", "-R", str(target)],
            {"check": False, "capture_output": True, "text": True},
        )
    ]


def test_terminal_open_uses_an_argument_vector_and_validates_cwd(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd = tmp_path / "workspace; touch not-executed"
    cwd.mkdir()
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(command: list[str], **kwargs: Any) -> CompletedProcess[str]:
        calls.append((command, kwargs))
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(desktop_bridge.subprocess, "run", fake_run)

    assert desktop_bridge.shell_open_terminal(str(cwd)) == {
        "success": True,
        "cwd": str(cwd),
    }
    assert calls == [
        (
            ["open", "-a", "Terminal", str(cwd)],
            {"check": False, "capture_output": True, "text": True},
        )
    ]

    calls.clear()
    invalid_result = desktop_bridge.shell_open_terminal(str(tmp_path / "missing"))
    assert invalid_result == {
        "success": False,
        "error": f"Terminal working directory does not exist: {tmp_path / 'missing'}",
    }
    assert calls == []


def test_malformed_paths_are_structured_application_failures() -> None:
    reveal_response = desktop_bridge.handle_request(
        {"id": 1, "method": "finder.reveal", "params": {"path": ""}}
    )
    terminal_response = desktop_bridge.handle_request(
        {"id": 2, "method": "shell.openTerminal", "params": {"cwd": "bad\0path"}}
    )

    assert reveal_response == {
        "id": 1,
        "result": {"success": False, "error": "Finder path must be a non-empty string"},
    }
    assert terminal_response == {
        "id": 2,
        "result": {
            "success": False,
            "error": "Terminal working directory contains an unsupported null character",
        },
    }
