# SDK contract tests for governance_supervision module

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from mutx.governance_supervision import (
    GovernanceSupervision,
    LaunchProfile,
    SupervisedAgent,
)
from tests.sdk_contract_utils import assert_v1_request


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _agent_response(**overrides):
    payload = {
        "agent_id": str(uuid.uuid4()),
        "status": "running",
        "pid": 12345,
        "started_at": "2024-01-01T00:00:00Z",
        "restart_count": 0,
    }
    payload.update(overrides)
    return payload


def _profile_response(**overrides):
    payload = {
        "name": "default",
        "command": ["python", "agent.py"],
        "env_keys": ["OPENAI_API_KEY"],
        "faramesh_policy": "strict",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Data-class tests
# ---------------------------------------------------------------------------


def test_supervised_agent_parses_response():
    data = _agent_response(agent_id="agent-001", status="running", pid=9999)
    agent = SupervisedAgent(data)

    assert agent.agent_id == "agent-001"
    assert agent.status == "running"
    assert agent.pid == 9999
    assert agent.started_at == "2024-01-01T00:00:00Z"
    assert agent.restart_count == 0


def test_supervised_agent_defaults():
    agent = SupervisedAgent({})

    assert agent.agent_id == ""
    assert agent.status == ""
    assert agent.pid is None
    assert agent.started_at is None
    assert agent.restart_count == 0


def test_supervised_agent_repr():
    agent = SupervisedAgent(_agent_response(agent_id="test-42", status="idle"))
    assert "test-42" in repr(agent)
    assert "idle" in repr(agent)


def test_launch_profile_parses_response():
    data = _profile_response(
        name="prod-agent",
        command=["node", "index.js"],
        env_keys=["KEY"],
        faramesh_policy="permissive",
    )
    profile = LaunchProfile(data)

    assert profile.name == "prod-agent"
    assert profile.command == ["node", "index.js"]
    assert profile.env_keys == ["KEY"]
    assert profile.faram_mesh_policy == "permissive"


def test_launch_profile_required_fields():
    data = {"name": "minimal", "command": ["echo", "hello"]}
    profile = LaunchProfile(data)

    assert profile.name == "minimal"
    assert profile.command == ["echo", "hello"]
    assert profile.env_keys == []
    assert profile.faram_mesh_policy is None


# ---------------------------------------------------------------------------
# Sync client tests — require httpx.Client
# ---------------------------------------------------------------------------


def test_list_agents_hits_contract_route():
    captured = {}

    def mock_get(*args, **kwargs):
        captured["path"] = args[1] if len(args) > 1 else args[0] if args else ""
        response = httpx.Response(
            200, json=[_agent_response(), _agent_response(agent_id="agent-002")]
        )
        response.raise_for_status = lambda: None
        return response

    with patch("mutx.governance_supervision.httpx.Client") as mock_client:
        mock_instance = mock_client.return_value.__enter__.return_value
        mock_instance.get.side_effect = mock_get

        gs = GovernanceSupervision.__new__(GovernanceSupervision)
        gs._client = mock_instance
        agents = gs.list_agents()

    assert_v1_request(
        mock_instance.get,
        "GET",
        "/v1/runtime/governance/supervised/",
    )
    assert len(agents) == 2
    assert all(isinstance(a, SupervisedAgent) for a in agents)


def test_list_agents_requires_sync_client():
    gs = GovernanceSupervision.__new__(GovernanceSupervision)
    # AsyncMock() is not isinstance(httpx.AsyncClient) so we must use a real one
    gs._client = httpx.AsyncClient()

    with pytest.raises(RuntimeError, match="sync httpx.Client"):
        gs.list_agents()


def test_list_profiles_hits_contract_route():
    captured = {}

    def mock_get(*args, **kwargs):
        captured["path"] = args[1] if len(args) > 1 else args[0] if args else ""
        response = httpx.Response(
            200, json=[_profile_response(), _profile_response(name="secondary")]
        )
        response.raise_for_status = lambda: None
        return response

    with patch("mutx.governance_supervision.httpx.Client") as mock_client:
        mock_instance = mock_client.return_value.__enter__.return_value
        mock_instance.get.side_effect = mock_get

        gs = GovernanceSupervision.__new__(GovernanceSupervision)
        gs._client = mock_instance
        profiles = gs.list_profiles()

    assert_v1_request(
        mock_instance.get,
        "GET",
        "/v1/runtime/governance/supervised/profiles",
    )
    assert len(profiles) == 2
    assert all(isinstance(p, LaunchProfile) for p in profiles)


def test_list_profiles_requires_sync_client():
    gs = GovernanceSupervision.__new__(GovernanceSupervision)
    gs._client = httpx.AsyncClient()

    with pytest.raises(RuntimeError, match="sync httpx.Client"):
        gs.list_profiles()


def test_get_agent_hits_contract_route():
    captured = {}
    agent_id = str(uuid.uuid4())

    def mock_get(*args, **kwargs):
        captured["path"] = args[1] if len(args) > 1 else args[0] if args else ""
        captured["agent_id"] = agent_id
        response = httpx.Response(200, json=_agent_response(agent_id=agent_id))
        response.raise_for_status = lambda: None
        return response

    with patch("mutx.governance_supervision.httpx.Client") as mock_client:
        mock_instance = mock_client.return_value.__enter__.return_value
        mock_instance.get.side_effect = mock_get

        gs = GovernanceSupervision.__new__(GovernanceSupervision)
        gs._client = mock_instance
        agent = gs.get_agent(agent_id=agent_id)

    assert_v1_request(
        mock_instance.get,
        "GET",
        f"/v1/runtime/governance/supervised/{agent_id}",
    )
    assert isinstance(agent, SupervisedAgent)
    assert agent.agent_id == agent_id


def test_get_agent_requires_sync_client():
    gs = GovernanceSupervision.__new__(GovernanceSupervision)
    gs._client = httpx.AsyncClient()

    with pytest.raises(RuntimeError, match="sync httpx.Client"):
        gs.get_agent(agent_id="any-id")


def test_start_agent_hits_contract_route():
    captured = {}
    agent_id = str(uuid.uuid4())

    def mock_post(*args, **kwargs):
        captured["path"] = args[1] if len(args) > 1 else args[0] if args else ""
        captured["json"] = kwargs.get("json", {})
        response = httpx.Response(200, json=_agent_response(agent_id=agent_id, status="running"))
        response.raise_for_status = lambda: None
        return response

    with patch("mutx.governance_supervision.httpx.Client") as mock_client:
        mock_instance = mock_client.return_value.__enter__.return_value
        mock_instance.post.side_effect = mock_post

        gs = GovernanceSupervision.__new__(GovernanceSupervision)
        gs._client = mock_instance
        agent = gs.start_agent(
            agent_id=agent_id,
            command=["python", "run.py"],
            profile="default",
            env={"KEY": "val"},
            faramesh_policy="strict",
        )

    assert_v1_request(
        mock_instance.post,
        "POST",
        "/v1/runtime/governance/supervised/start",
    )
    assert captured["json"]["agent_id"] == agent_id
    assert captured["json"]["command"] == ["python", "run.py"]
    assert captured["json"]["profile"] == "default"
    assert captured["json"]["env"] == {"KEY": "val"}
    assert captured["json"]["faramesh_policy"] == "strict"
    assert isinstance(agent, SupervisedAgent)


def test_start_agent_minimal_payload():
    captured = {}

    def mock_post(*args, **kwargs):
        captured["json"] = kwargs.get("json", {})
        response = httpx.Response(200, json=_agent_response())
        response.raise_for_status = lambda: None
        return response

    with patch("mutx.governance_supervision.httpx.Client") as mock_client:
        mock_instance = mock_client.return_value.__enter__.return_value
        mock_instance.post.side_effect = mock_post

        gs = GovernanceSupervision.__new__(GovernanceSupervision)
        gs._client = mock_instance
        gs.start_agent(agent_id="minimal", command=["echo", "hi"])

    assert captured["json"]["agent_id"] == "minimal"
    assert captured["json"]["command"] == ["echo", "hi"]
    assert "profile" not in captured["json"]
    assert "env" not in captured["json"]
    assert "faramesh_policy" not in captured["json"]


def test_start_agent_requires_sync_client():
    gs = GovernanceSupervision.__new__(GovernanceSupervision)
    gs._client = httpx.AsyncClient()

    with pytest.raises(RuntimeError, match="sync httpx.Client"):
        gs.start_agent(agent_id="x", command=["echo"])


def test_stop_agent_hits_contract_route():
    captured = {}
    agent_id = str(uuid.uuid4())

    def mock_post(*args, **kwargs):
        captured["path"] = args[1] if len(args) > 1 else args[0] if args else ""
        captured["json"] = kwargs.get("json", {})
        response = httpx.Response(200, json={"status": "stopped"})
        response.raise_for_status = lambda: None
        return response

    with patch("mutx.governance_supervision.httpx.Client") as mock_client:
        mock_instance = mock_client.return_value.__enter__.return_value
        mock_instance.post.side_effect = mock_post

        gs = GovernanceSupervision.__new__(GovernanceSupervision)
        gs._client = mock_instance
        result = gs.stop_agent(agent_id=agent_id, timeout=30.0)

    assert_v1_request(
        mock_instance.post,
        "POST",
        f"/v1/runtime/governance/supervised/{agent_id}/stop",
    )
    assert captured["json"]["timeout"] == 30.0
    assert isinstance(result, dict)


def test_stop_agent_default_timeout():
    captured = {}

    def mock_post(*args, **kwargs):
        captured["json"] = kwargs.get("json", {})
        response = httpx.Response(200, json={"status": "stopped"})
        response.raise_for_status = lambda: None
        return response

    with patch("mutx.governance_supervision.httpx.Client") as mock_client:
        mock_instance = mock_client.return_value.__enter__.return_value
        mock_instance.post.side_effect = mock_post

        gs = GovernanceSupervision.__new__(GovernanceSupervision)
        gs._client = mock_instance
        gs.stop_agent(agent_id="x")

    assert captured["json"]["timeout"] == 10.0


def test_stop_agent_requires_sync_client():
    gs = GovernanceSupervision.__new__(GovernanceSupervision)
    gs._client = httpx.AsyncClient()

    with pytest.raises(RuntimeError, match="sync httpx.Client"):
        gs.stop_agent(agent_id="x")


def test_restart_agent_hits_contract_route():
    captured = {}
    agent_id = str(uuid.uuid4())

    def mock_post(*args, **kwargs):
        captured["path"] = args[1] if len(args) > 1 else args[0] if args else ""
        response = httpx.Response(200, json=_agent_response(agent_id=agent_id))
        response.raise_for_status = lambda: None
        return response

    with patch("mutx.governance_supervision.httpx.Client") as mock_client:
        mock_instance = mock_client.return_value.__enter__.return_value
        mock_instance.post.side_effect = mock_post

        gs = GovernanceSupervision.__new__(GovernanceSupervision)
        gs._client = mock_instance
        agent = gs.restart_agent(agent_id=agent_id)

    assert_v1_request(
        mock_instance.post,
        "POST",
        f"/v1/runtime/governance/supervised/{agent_id}/restart",
    )
    assert isinstance(agent, SupervisedAgent)
    assert agent.agent_id == agent_id


def test_restart_agent_requires_sync_client():
    gs = GovernanceSupervision.__new__(GovernanceSupervision)
    gs._client = httpx.AsyncClient()

    with pytest.raises(RuntimeError, match="sync httpx.Client"):
        gs.restart_agent(agent_id="x")


# ---------------------------------------------------------------------------
# Async client tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alist_agents_hits_contract_route():
    captured = {}

    async def mock_get(*args, **kwargs):
        captured["path"] = args[1] if len(args) > 1 else args[0] if args else ""
        response = AsyncMock()
        response.raise_for_status = lambda: None
        response.json = lambda: [_agent_response()]
        return response

    # Use real httpx.AsyncClient so isinstance check passes; mock the method
    client = httpx.AsyncClient()
    client.get = AsyncMock(side_effect=mock_get)

    gs = GovernanceSupervision.__new__(GovernanceSupervision)
    gs._client = client
    agents = await gs.alist_agents()

    assert_v1_request(client.get, "GET", "/v1/runtime/governance/supervised/")
    assert len(agents) == 1
    assert isinstance(agents[0], SupervisedAgent)


@pytest.mark.asyncio
async def test_alist_agents_requires_async_client():
    gs = GovernanceSupervision.__new__(GovernanceSupervision)
    gs._client = httpx.Client()

    with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
        await gs.alist_agents()


@pytest.mark.asyncio
async def test_alist_profiles_hits_contract_route():
    captured = {}

    async def mock_get(*args, **kwargs):
        captured["path"] = args[1] if len(args) > 1 else args[0] if args else ""
        response = AsyncMock()
        response.raise_for_status = lambda: None
        response.json = lambda: [_profile_response(), _profile_response(name="alt")]
        return response

    client = httpx.AsyncClient()
    client.get = AsyncMock(side_effect=mock_get)

    gs = GovernanceSupervision.__new__(GovernanceSupervision)
    gs._client = client
    profiles = await gs.alist_profiles()

    assert_v1_request(
        client.get,
        "GET",
        "/v1/runtime/governance/supervised/profiles",
    )
    assert len(profiles) == 2
    assert all(isinstance(p, LaunchProfile) for p in profiles)


@pytest.mark.asyncio
async def test_alist_profiles_requires_async_client():
    gs = GovernanceSupervision.__new__(GovernanceSupervision)
    gs._client = httpx.Client()

    with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
        await gs.alist_profiles()


@pytest.mark.asyncio
async def test_aget_agent_hits_contract_route():
    captured = {}
    agent_id = str(uuid.uuid4())

    async def mock_get(*args, **kwargs):
        captured["path"] = args[1] if len(args) > 1 else args[0] if args else ""
        response = AsyncMock()
        response.raise_for_status = lambda: None
        response.json = lambda: _agent_response(agent_id=agent_id)
        return response

    client = httpx.AsyncClient()
    client.get = AsyncMock(side_effect=mock_get)

    gs = GovernanceSupervision.__new__(GovernanceSupervision)
    gs._client = client
    agent = await gs.aget_agent(agent_id=agent_id)

    assert_v1_request(
        client.get,
        "GET",
        f"/v1/runtime/governance/supervised/{agent_id}",
    )
    assert isinstance(agent, SupervisedAgent)
    assert agent.agent_id == agent_id


@pytest.mark.asyncio
async def test_aget_agent_requires_async_client():
    gs = GovernanceSupervision.__new__(GovernanceSupervision)
    gs._client = httpx.Client()

    with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
        await gs.aget_agent(agent_id="x")


@pytest.mark.asyncio
async def test_astar_agent_hits_contract_route():
    captured = {}
    agent_id = str(uuid.uuid4())

    async def mock_post(*args, **kwargs):
        captured["path"] = args[1] if len(args) > 1 else args[0] if args else ""
        captured["json"] = kwargs.get("json", {})
        response = AsyncMock()
        response.raise_for_status = lambda: None
        response.json = lambda: _agent_response(agent_id=agent_id, status="running")
        return response

    client = httpx.AsyncClient()
    client.post = AsyncMock(side_effect=mock_post)

    gs = GovernanceSupervision.__new__(GovernanceSupervision)
    gs._client = client
    agent = await gs.astart_agent(
        agent_id=agent_id,
        command=["python", "agent.py"],
        profile="prod",
        env={"SECRET": "xyz"},
        faramesh_policy="strict",
    )

    assert_v1_request(
        client.post,
        "POST",
        "/v1/runtime/governance/supervised/start",
    )
    assert captured["json"]["agent_id"] == agent_id
    assert captured["json"]["command"] == ["python", "agent.py"]
    assert captured["json"]["profile"] == "prod"
    assert captured["json"]["env"] == {"SECRET": "xyz"}
    assert captured["json"]["faramesh_policy"] == "strict"
    assert isinstance(agent, SupervisedAgent)


@pytest.mark.asyncio
async def test_astar_agent_requires_async_client():
    gs = GovernanceSupervision.__new__(GovernanceSupervision)
    gs._client = httpx.Client()

    with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
        await gs.astart_agent(agent_id="x", command=["echo"])


@pytest.mark.asyncio
async def test_astop_agent_hits_contract_route():
    captured = {}
    agent_id = str(uuid.uuid4())

    async def mock_post(*args, **kwargs):
        captured["path"] = args[1] if len(args) > 1 else args[0] if args else ""
        captured["json"] = kwargs.get("json", {})
        response = AsyncMock()
        response.raise_for_status = lambda: None
        response.json = lambda: {"status": "stopped"}
        return response

    client = httpx.AsyncClient()
    client.post = AsyncMock(side_effect=mock_post)

    gs = GovernanceSupervision.__new__(GovernanceSupervision)
    gs._client = client
    result = await gs.astop_agent(agent_id=agent_id, timeout=15.0)

    assert_v1_request(
        client.post,
        "POST",
        f"/v1/runtime/governance/supervised/{agent_id}/stop",
    )
    assert captured["json"]["timeout"] == 15.0
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_astop_agent_requires_async_client():
    gs = GovernanceSupervision.__new__(GovernanceSupervision)
    gs._client = httpx.Client()

    with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
        await gs.astop_agent(agent_id="x")


@pytest.mark.asyncio
async def test_arestart_agent_hits_contract_route():
    captured = {}
    agent_id = str(uuid.uuid4())

    async def mock_post(*args, **kwargs):
        captured["path"] = args[1] if len(args) > 1 else args[0] if args else ""
        response = AsyncMock()
        response.raise_for_status = lambda: None
        response.json = lambda: _agent_response(agent_id=agent_id)
        return response

    client = httpx.AsyncClient()
    client.post = AsyncMock(side_effect=mock_post)

    gs = GovernanceSupervision.__new__(GovernanceSupervision)
    gs._client = client
    agent = await gs.arestart_agent(agent_id=agent_id)

    assert_v1_request(
        client.post,
        "POST",
        f"/v1/runtime/governance/supervised/{agent_id}/restart",
    )
    assert isinstance(agent, SupervisedAgent)
    assert agent.agent_id == agent_id


@pytest.mark.asyncio
async def test_arestart_agent_requires_async_client():
    gs = GovernanceSupervision.__new__(GovernanceSupervision)
    gs._client = httpx.Client()

    with pytest.raises(RuntimeError, match="async httpx.AsyncClient"):
        await gs.arestart_agent(agent_id="x")
