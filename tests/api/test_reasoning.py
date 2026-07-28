from __future__ import annotations

import io
from datetime import timedelta

import pytest


@pytest.fixture(autouse=True)
def enable_reasoning_workflows(monkeypatch, tmp_path, test_user):
    from src.api.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "reasoning_enabled", True)
    monkeypatch.setattr(settings, "artifacts_dir", str(tmp_path / "artifacts"))
    monkeypatch.setattr(settings, "reasoning_max_upload_mb", 10)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    test_user.roles = ["DEVELOPER"]
    yield


@pytest.fixture
def stub_reasoning_model(monkeypatch):
    async def fake_invoke_model(
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 0,
    ) -> dict[str, object]:
        normalized_system = system_prompt.lower()
        if "initial author" in normalized_system:
            return {
                "text": "Initial answer with a concrete operating plan.",
                "usage": {"input_tokens": 11, "output_tokens": 14, "total_tokens": 25},
                "provider": "test",
            }
        if "critical reviewer" in normalized_system:
            return {
                "text": "- Tighten the success criteria\n- Remove generic filler",
                "usage": {"input_tokens": 9, "output_tokens": 10, "total_tokens": 19},
                "provider": "test",
            }
        if "revision author" in normalized_system:
            return {
                "text": "Revised answer with explicit success criteria and less filler.",
                "usage": {"input_tokens": 10, "output_tokens": 12, "total_tokens": 22},
                "provider": "test",
            }
        if "synthesizer" in normalized_system:
            return {
                "text": "Synthesized answer with concrete steps, success criteria, and cleaner structure.",
                "usage": {"input_tokens": 10, "output_tokens": 13, "total_tokens": 23},
                "provider": "test",
            }
        if "independent judge" in normalized_system:
            return {
                "text": '{"ranking": ["AB", "A", "B"], "rationale": "AB is the strongest overall answer."}',
                "usage": {"input_tokens": 12, "output_tokens": 15, "total_tokens": 27},
                "provider": "test",
            }
        raise AssertionError(f"Unexpected system prompt: {system_prompt}")

    monkeypatch.setattr(
        "src.api.services.reasoning_engine._invoke_model",
        fake_invoke_model,
    )


@pytest.mark.asyncio
async def test_reasoning_template_catalog_returns_expected_templates(client):
    response = await client.get("/v1/reasoning/templates")

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload] == ["autoreason_refine"]


@pytest.mark.asyncio
async def test_reasoning_job_dispatch_validates_required_inputs(client):
    create_response = await client.post(
        "/v1/reasoning/jobs",
        json={
            "template_id": "autoreason_refine",
            "execution_mode": "managed",
            "parameters": {},
        },
    )
    assert create_response.status_code == 201
    job_id = create_response.json()["id"]

    dispatch_response = await client.post(
        f"/v1/reasoning/jobs/{job_id}/dispatch",
        json={"mode": "managed"},
    )

    assert dispatch_response.status_code == 400
    assert "Missing required reasoning inputs" in dispatch_response.json()["detail"]


@pytest.mark.asyncio
async def test_reasoning_artifact_upload_and_download_are_user_scoped(client, other_user_client):
    create_response = await client.post(
        "/v1/reasoning/jobs",
        json={
            "template_id": "autoreason_refine",
            "execution_mode": "managed",
            "parameters": {"task_prompt": "Refine this answer"},
        },
    )
    assert create_response.status_code == 201
    job_id = create_response.json()["id"]

    upload_response = await client.post(
        f"/v1/reasoning/jobs/{job_id}/artifacts",
        files={"file": ("context.txt", io.BytesIO(b"market context"), "text/plain")},
        data={"role": "context", "kind": "file"},
    )
    assert upload_response.status_code == 201
    artifact = upload_response.json()

    download_response = await client.get(f"/v1/reasoning/jobs/{job_id}/artifacts/{artifact['id']}")
    assert download_response.status_code == 200
    assert download_response.content == b"market context"

    forbidden_response = await other_user_client.get(
        f"/v1/reasoning/jobs/{job_id}/artifacts/{artifact['id']}"
    )
    assert forbidden_response.status_code == 404


@pytest.mark.asyncio
async def test_managed_reasoning_lifecycle_executes_through_worker(
    client,
    db_session,
    stub_reasoning_model,
):
    from src.api.services.reasoning_jobs import claim_next_reasoning_job, execute_reasoning_job

    create_response = await client.post(
        "/v1/reasoning/jobs",
        json={
            "template_id": "autoreason_refine",
            "execution_mode": "managed",
            "parameters": {
                "task_prompt": "Write a tighter launch memo for MUTX.",
                "incumbent": "Initial answer with loose structure.",
                "max_passes": 3,
                "judge_count": 3,
                "convergence_wins": 2,
            },
        },
    )
    assert create_response.status_code == 201
    job = create_response.json()

    dispatch_response = await client.post(
        f"/v1/reasoning/jobs/{job['id']}/dispatch",
        json={"mode": "managed"},
    )
    assert dispatch_response.status_code == 200
    assert dispatch_response.json()["status"] == "queued"

    claimed = await claim_next_reasoning_job(db_session, worker_name="test-reasoning-worker")
    assert claimed is not None
    executed = await execute_reasoning_job(db_session, claimed_job=claimed)

    assert executed.status == "completed"
    assert executed.run.status == "completed"
    assert any(artifact.role == "final_output" for artifact in executed.artifacts)
    assert any(artifact.role == "pass_log" for artifact in executed.artifacts)
    assert executed.result_summary["winner"] in {"A", "B", "AB"}
    assert executed.result_summary["pass_count"] >= 1

    job_response = await client.get(f"/v1/reasoning/jobs/{job['id']}")
    assert job_response.status_code == 200
    job_payload = job_response.json()
    assert job_payload["status"] == "completed"
    assert any(artifact["role"] == "judge_ballots" for artifact in job_payload["artifacts"])

    run_response = await client.get(f"/v1/runs/{job['run_id']}")
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["agent_id"] is None
    assert run_payload["subject_type"] == "reasoning_job"
    assert run_payload["subject_id"] == job["id"]
    assert run_payload["template_id"] == "autoreason_refine"
    assert run_payload["execution_mode"] == "managed"
    assert any(trace["event_type"] == "reasoning.completed" for trace in run_payload["traces"])


@pytest.mark.asyncio
async def test_stale_running_reasoning_job_is_reclaimed(client, db_session):
    from src.api.services.reasoning_jobs import claim_next_reasoning_job

    create_response = await client.post(
        "/v1/reasoning/jobs",
        json={
            "template_id": "autoreason_refine",
            "execution_mode": "managed",
            "parameters": {
                "task_prompt": "Write a tighter launch memo for MUTX.",
                "incumbent": "Initial answer with loose structure.",
            },
        },
    )
    assert create_response.status_code == 201
    job_id = create_response.json()["id"]

    dispatch_response = await client.post(
        f"/v1/reasoning/jobs/{job_id}/dispatch",
        json={"mode": "managed"},
    )
    assert dispatch_response.status_code == 200

    first_claim = await claim_next_reasoning_job(db_session, worker_name="worker-one")
    assert first_claim is not None

    stale_heartbeat = first_claim.job.last_heartbeat_at - timedelta(seconds=600)
    first_claim.job.claimed_by = "worker-one"
    first_claim.job.claimed_at = stale_heartbeat
    first_claim.job.last_heartbeat_at = stale_heartbeat
    first_claim.job.run.status = "running"
    await db_session.commit()

    reclaimed = await claim_next_reasoning_job(
        db_session,
        worker_name="worker-two",
        stale_after_seconds=60,
    )

    assert reclaimed is not None
    assert reclaimed.job.id == first_claim.job.id
    assert reclaimed.worker_name == "worker-two"
    assert reclaimed.claim_token != first_claim.claim_token
    assert reclaimed.job.claimed_by == "worker-two"
    assert reclaimed.job.attempts == 2


@pytest.mark.asyncio
async def test_local_reasoning_lifecycle_supports_events_and_uploaded_outputs(client):
    create_response = await client.post(
        "/v1/reasoning/jobs",
        json={
            "template_id": "autoreason_refine",
            "execution_mode": "local",
            "parameters": {"task_prompt": "Refine this memo locally."},
        },
    )
    assert create_response.status_code == 201
    job = create_response.json()

    register_response = await client.post(
        f"/v1/reasoning/jobs/{job['id']}/artifacts",
        json={
            "role": "context",
            "kind": "file",
            "storage_backend": "local_reference",
            "filename": "context.txt",
            "local_path": "/tmp/context.txt",
            "metadata": {},
        },
    )
    assert register_response.status_code == 201

    launch_response = await client.post(
        f"/v1/reasoning/jobs/{job['id']}/launch-local",
        json={"output_dir": "/tmp/mutx-local-reasoning"},
    )
    assert launch_response.status_code == 200
    assert launch_response.json()["manifest"]["template_id"] == "autoreason_refine"

    running_response = await client.post(
        f"/v1/reasoning/jobs/{job['id']}/events",
        json={
            "event_type": "reasoning.pass_started",
            "message": "Local reasoning started",
            "status": "running",
        },
    )
    assert running_response.status_code == 200
    assert running_response.json()["status"] == "running"

    upload_response = await client.post(
        f"/v1/reasoning/jobs/{job['id']}/artifacts",
        files={
            "file": (
                "final.md",
                io.BytesIO(b"# Final\n\nLocal autoreason output."),
                "text/markdown",
            )
        },
        data={"role": "final_output", "kind": "markdown"},
    )
    assert upload_response.status_code == 201

    complete_response = await client.post(
        f"/v1/reasoning/jobs/{job['id']}/events",
        json={
            "event_type": "reasoning.completed",
            "message": "Local reasoning finished",
            "status": "completed",
            "output_text": "Local autoreason complete",
            "result_summary": {"winner": "AB", "pass_count": 2},
        },
    )
    assert complete_response.status_code == 200
    payload = complete_response.json()
    assert payload["status"] == "completed"
    assert payload["result_summary"] == {"winner": "AB", "pass_count": 2}
    assert any(artifact["role"] == "final_output" for artifact in payload["artifacts"])


@pytest.mark.asyncio
async def test_reasoning_jobs_appear_in_runs_listing(client):
    create_response = await client.post(
        "/v1/reasoning/jobs",
        json={
            "template_id": "autoreason_refine",
            "execution_mode": "managed",
            "parameters": {"task_prompt": "Produce a better release note."},
        },
    )
    assert create_response.status_code == 201
    job = create_response.json()

    runs_response = await client.get("/v1/runs")
    assert runs_response.status_code == 200
    runs = runs_response.json()["items"]
    reasoning_run = next(item for item in runs if item["id"] == job["run_id"])
    assert reasoning_run["agent_id"] is None
    assert reasoning_run["subject_label"] == "Autoreason Refine"
    assert reasoning_run["template_id"] == "autoreason_refine"


@pytest.mark.asyncio
async def test_builtin_reasoning_summary_reports_actual_winner(monkeypatch):
    from src.api.services.reasoning_engine import execute_reasoning_manifest

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    manifest = {
        "template_id": "autoreason_refine",
        "parameters": {
            "task_prompt": "Turn this into a concrete operator plan.",
            "incumbent": "A vague answer.",
            "max_passes": 1,
            "judge_count": 1,
            "convergence_wins": 2,
            "rubric": "Concrete, structured, no filler.",
        },
        "artifacts": [],
        "output_dir": None,
    }

    result = await execute_reasoning_manifest(manifest)

    assert result.output_text != "A vague answer."
    assert result.summary["winner"] != "A"
