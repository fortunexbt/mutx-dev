from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import re
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, status
from opentelemetry.trace import Status, StatusCode
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import get_settings
from src.api.models import User
from src.api.models.pico_tutor import (
    PicoTutorCommand,
    PicoTutorConfidence,
    PicoTutorDocLink,
    PicoTutorEntitlement,
    PicoTutorGenerationProof,
    PicoTutorGuidance,
    PicoTutorIntent,
    PicoTutorLessonLink,
    PicoTutorRequest,
    PicoTutorResponse,
    PicoTutorSkillLevel,
    PicoTutorSource,
    PicoTutorStructuredReply,
)
from src.api.telemetry.telemetry import get_tracer
from src.api.services.pico_tutor_openai import (
    require_pico_tutor_access,
    resolve_pico_tutor_api_key,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class _MissingAsyncOpenAI:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError(
            "openai package is not installed; install project dependencies to use Pico tutor"
        )


try:
    from openai import AsyncOpenAI
except ModuleNotFoundError:
    AsyncOpenAI = _MissingAsyncOpenAI


@dataclass(frozen=True)
class PicoTutorGenerationFailure:
    status_code: int
    code: str
    message: str


KNOWLEDGE_ROOT = Path(__file__).resolve().parents[1] / "knowledge" / "pico_ops"
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_./+-]*")
CODE_BLOCK_RE = re.compile(r"```(?P<lang>[a-zA-Z0-9_-]+)?\n(?P<code>.*?)```", re.DOTALL)
LIST_ITEM_RE = re.compile(r"^\s*[-*]\s+(?P<item>.+?)\s*$", re.MULTILINE)
URL_RE = re.compile(r"^https?://", re.IGNORECASE)

INTENT_KEYWORDS: dict[PicoTutorIntent, tuple[str, ...]] = {
    "choose": ("which", "best", "recommend", "compare", "difference", "pick", "choose"),
    "install": ("install", "setup", "bootstrap", "start", "fresh install"),
    "repair": ("broken", "not working", "fails", "error", "issue", "repair", "fix", "debug"),
    "migrate": ("migrate", "move from", "switch from", "port over"),
    "compare": ("compare", "versus", "vs", "tradeoff"),
    "tailscale": ("tailscale", "tailnet", "ssh", "remote access", "magicdns"),
    "optimize": ("optimize", "performance", "memory", "tune", "speed", "cost"),
    "integrate": ("integrate", "provider", "model", "gateway", "discord", "telegram", "slack"),
}

SKILL_KEYWORDS: dict[PicoTutorSkillLevel, tuple[str, ...]] = {
    "beginner": ("beginner", "new", "first time", "step by step", "never done this"),
    "advanced": ("ssh", "docker", "systemd", "compose", "wsl", "reverse proxy", "subnet"),
}

RISKY_KEYWORDS = (
    "delete",
    "wipe",
    "destroy",
    "production",
    "billing",
    "payment",
    "secret",
    "token",
    "credential",
    "breach",
    "firewall",
    "expose",
    "public internet",
    "disable",
    "root access",
)

VERSION_SENSITIVE_KEYWORDS = (
    "latest",
    "version",
    "release",
    "pricing",
    "supported",
    "flag",
    "cli flag",
    "api server",
    "oauth",
    "docker image",
    "install command",
)

DIRECT_LESSON_KEYWORDS: dict[str, tuple[str, ...]] = {
    "install-hermes-locally": ("install hermes", "hermes install", "command -v hermes"),
    "run-your-first-agent": ("first prompt", "first agent", "save transcript"),
    "deploy-hermes-on-a-vps": ("vps", "deploy hermes", "always on"),
    "keep-your-agent-alive": ("keep alive", "close ssh", "systemd", "tmux", "survive reboot"),
    "connect-a-messaging-layer": ("discord", "telegram", "slack", "messaging"),
    "add-your-first-skill": ("skill", "tool", "capability"),
    "create-a-scheduled-workflow": ("schedule", "cron", "workflow", "automation"),
    "see-your-agent-activity": ("run history", "activity", "logs", "autopilot"),
    "set-a-cost-threshold": ("budget", "threshold", "cost"),
    "add-an-approval-gate": ("approval", "gate", "review before send"),
}


@dataclass(frozen=True)
class KnowledgeDoc:
    id: str
    title: str
    filename: str
    body: str
    topics: tuple[str, ...]
    agents: tuple[str, ...]
    intents: tuple[str, ...]
    official_fallback_expected: bool
    visible: bool
    official_links: tuple[str, ...]
    command_blocks: tuple[PicoTutorCommand, ...]


@dataclass(frozen=True)
class LessonDoc:
    slug: str
    title: str
    summary: str
    objective: str
    expected_result: str
    validation: str
    troubleshooting: tuple[str, ...]
    steps: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class RetrievalMatch:
    kind: Literal["lesson", "knowledge_pack"]
    id: str
    title: str
    score: int
    excerpt: str
    href: str | None = None
    source_path: str | None = None


@dataclass(frozen=True)
class OfficialEvidence:
    title: str
    href: str
    excerpt: str


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def _tokenize(value: str) -> list[str]:
    return [token for token in TOKEN_RE.findall(value.lower()) if len(token) > 1]


def _score_tokens(tokens: list[str], haystack: str, *, bonus: int = 0) -> int:
    score = 0
    lowered = haystack.lower()
    for token in tokens:
        if token in lowered:
            score += 2
    return score + bonus


def _extract_markdown_title(body: str, fallback: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def _extract_official_links(body: str) -> tuple[str, ...]:
    links: list[str] = []
    capture = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.lower() == "## official sources":
            capture = True
            continue
        if capture and stripped.startswith("## "):
            break
        if capture and stripped.startswith("- "):
            candidate = stripped[2:].strip()
            if URL_RE.match(candidate):
                links.append(candidate)
    return tuple(dict.fromkeys(links))


def _extract_command_blocks(body: str) -> tuple[PicoTutorCommand, ...]:
    commands: list[PicoTutorCommand] = []
    for index, match in enumerate(CODE_BLOCK_RE.finditer(body)):
        code = match.group("code").strip()
        if not code:
            continue
        language = (match.group("lang") or "bash").strip().lower() or "bash"
        commands.append(
            PicoTutorCommand(
                label=f"Reference command {index + 1}",
                code=code,
                language=language,
            )
        )
    return tuple(commands[:3])


@lru_cache(maxsize=1)
def load_manifest() -> dict[str, Any]:
    return _read_json(KNOWLEDGE_ROOT / "manifest.json")


@lru_cache(maxsize=1)
def load_system_prompt() -> str:
    return (KNOWLEDGE_ROOT / "SYSTEM_PROMPT.md").read_text("utf-8").strip()


@lru_cache(maxsize=1)
def load_knowledge_docs() -> tuple[KnowledgeDoc, ...]:
    manifest = load_manifest()
    docs: list[KnowledgeDoc] = []
    for entry in manifest.get("docs", []):
        filename = entry["filename"]
        path = KNOWLEDGE_ROOT / filename
        body = path.read_text("utf-8")
        docs.append(
            KnowledgeDoc(
                id=entry["id"],
                title=_extract_markdown_title(body, filename.replace(".md", "").replace("_", " ")),
                filename=filename,
                body=body,
                topics=tuple(entry.get("topics", [])),
                agents=tuple(entry.get("agents", [])),
                intents=tuple(entry.get("intents", [])),
                official_fallback_expected=bool(entry.get("officialFallbackExpected")),
                visible=bool(entry.get("visible", True)),
                official_links=tuple(entry.get("officialLinks", []))
                or _extract_official_links(body),
                command_blocks=_extract_command_blocks(body),
            )
        )
    return tuple(docs)


@lru_cache(maxsize=1)
def load_lesson_docs() -> tuple[LessonDoc, ...]:
    payload = _read_json(KNOWLEDGE_ROOT / "pico_lessons.json")
    docs: list[LessonDoc] = []
    for item in payload:
        docs.append(
            LessonDoc(
                slug=item["slug"],
                title=item["title"],
                summary=item["summary"],
                objective=item["objective"],
                expected_result=item["expectedResult"],
                validation=item["validation"],
                troubleshooting=tuple(item.get("troubleshooting", [])),
                steps=tuple(item.get("steps", [])),
            )
        )
    return tuple(docs)


def classify_intent(question: str, lesson_slug: str | None = None) -> PicoTutorIntent:
    lowered = question.lower()
    scores = {intent: 0 for intent in INTENT_KEYWORDS}
    for intent, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in lowered:
                scores[intent] += 3 if " " in keyword else 2

    if lesson_slug:
        if "install" in lesson_slug:
            scores["install"] += 4
        if "approval" in lesson_slug or "cost" in lesson_slug:
            scores["optimize"] += 3
        if "schedule" in lesson_slug:
            scores["integrate"] += 3

    if any(keyword in lowered for keyword in ("tailscale", "tailnet", "magicdns")):
        scores["tailscale"] += 5

    intent, score = max(scores.items(), key=lambda item: item[1])
    if score <= 0:
        if any(
            keyword in lowered
            for keyword in ("error", "fail", "broken", "traceback", "not working")
        ):
            return "repair"
        return "install"
    return intent


def detect_skill_level(
    question: str, setup_context: dict[str, Any] | None = None
) -> PicoTutorSkillLevel:
    lowered = question.lower()
    for level, keywords in SKILL_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return level

    runtime = (setup_context or {}).get("runtime") if isinstance(setup_context, dict) else None
    if isinstance(runtime, dict) and runtime.get("gateway_url"):
        return "advanced"

    return "intermediate"


def detect_risk(question: str) -> str | None:
    lowered = question.lower()
    for keyword in RISKY_KEYWORDS:
        if keyword in {"expose", "public internet"} and (
            "without exposing" in lowered
            or "avoid exposing" in lowered
            or "keep it private" in lowered
            or "private tailnet" in lowered
        ):
            continue
        if keyword in lowered:
            return keyword
    return None


def is_version_sensitive(question: str) -> bool:
    lowered = question.lower()
    return any(keyword in lowered for keyword in VERSION_SENSITIVE_KEYWORDS)


def retrieve_lessons(question: str, lesson_slug: str | None = None) -> list[RetrievalMatch]:
    tokens = _tokenize(question)
    matches: list[RetrievalMatch] = []
    for lesson in load_lesson_docs():
        haystack = " ".join(
            [
                lesson.slug,
                lesson.title,
                lesson.summary,
                lesson.objective,
                lesson.expected_result,
                lesson.validation,
                *lesson.troubleshooting,
                *[
                    " ".join(
                        filter(
                            None,
                            [
                                step.get("title", ""),
                                step.get("body", ""),
                                step.get("command", ""),
                                step.get("note", ""),
                            ],
                        )
                    )
                    for step in lesson.steps
                ],
            ]
        )
        score = _score_tokens(tokens, haystack)
        if lesson.slug == lesson_slug:
            score += 10
        for keyword in DIRECT_LESSON_KEYWORDS.get(lesson.slug, ()):
            if keyword in question.lower():
                score += 4
        if score <= 0:
            continue
        matches.append(
            RetrievalMatch(
                kind="lesson",
                id=lesson.slug,
                title=lesson.title,
                score=score,
                excerpt=lesson.summary,
                href=f"/pico/academy/{lesson.slug}",
                source_path=f"pico/academy/{lesson.slug}",
            )
        )
    return sorted(matches, key=lambda item: item.score, reverse=True)[:4]


def retrieve_knowledge_docs(
    question: str,
    *,
    intent: PicoTutorIntent,
    version_sensitive: bool,
) -> list[RetrievalMatch]:
    tokens = _tokenize(question)
    lowered = question.lower()
    matches: list[RetrievalMatch] = []

    for doc in load_knowledge_docs():
        haystack = " ".join(
            [
                doc.title,
                doc.body,
                " ".join(doc.topics),
                " ".join(doc.agents),
                " ".join(doc.intents),
            ]
        )
        score = _score_tokens(tokens, haystack)
        if intent in doc.intents:
            score += 3
        if version_sensitive and doc.official_fallback_expected:
            score += 3
        if (
            doc.id in {"readme", "builder-setup"}
            and "builder" not in lowered
            and "pack" not in lowered
        ):
            score -= 4
        if score <= 0 or not doc.visible:
            continue
        excerpt = next(
            (item.strip() for item in LIST_ITEM_RE.findall(doc.body) if item.strip()), ""
        )
        excerpt = excerpt or doc.body.strip().splitlines()[0]
        matches.append(
            RetrievalMatch(
                kind="knowledge_pack",
                id=doc.id,
                title=doc.title,
                score=score,
                excerpt=excerpt[:240],
                source_path=f"knowledge/pico_ops/{doc.filename}",
            )
        )

    return sorted(matches, key=lambda item: item.score, reverse=True)[:4]


def get_lesson_by_slug(lesson_slug: str | None) -> LessonDoc | None:
    if not lesson_slug:
        return None
    return next((lesson for lesson in load_lesson_docs() if lesson.slug == lesson_slug), None)


def collect_official_links(matches: list[RetrievalMatch], intent: PicoTutorIntent) -> list[str]:
    links: list[str] = []
    docs_by_id = {doc.id: doc for doc in load_knowledge_docs()}
    for match in matches:
        if match.kind != "knowledge_pack":
            continue
        doc = docs_by_id.get(match.id)
        if doc:
            links.extend(doc.official_links)

    if intent == "tailscale" and not links:
        links.extend(["https://tailscale.com/download", "https://tailscale.com/kb"])

    deduped: list[str] = []
    for link in links:
        if URL_RE.match(link) and link not in deduped:
            deduped.append(link)
    return deduped[:3]


def _allowlisted_official_hosts() -> set[str]:
    hosts: set[str] = set()
    for doc in load_knowledge_docs():
        for link in doc.official_links:
            host = urlparse(link).netloc.lower()
            if host:
                hosts.add(host)
    hosts.update({"tailscale.com", "github.com"})
    return hosts


def _extract_web_text(payload: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", payload, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


async def fetch_official_evidence(url: str) -> OfficialEvidence | None:
    host = urlparse(url).netloc.lower()
    if host not in _allowlisted_official_hosts():
        return None

    async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
        response = await client.get(url, headers={"User-Agent": "MUTX Pico Tutor/1.0"})
        response.raise_for_status()
        payload = response.text

    if "<html" in payload.lower():
        title_match = re.search(r"<title>(.*?)</title>", payload, flags=re.IGNORECASE | re.DOTALL)
        title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else host
        excerpt = _extract_web_text(payload)[:320]
    else:
        lines = [line.strip() for line in payload.splitlines() if line.strip()]
        title = lines[0][:120] if lines else host
        excerpt = " ".join(lines[1:5])[:320]

    return OfficialEvidence(title=title, href=url, excerpt=excerpt or title)


def _confidence_from_scores(
    lesson_matches: list[RetrievalMatch],
    knowledge_matches: list[RetrievalMatch],
    *,
    risky: bool,
    asked_for_more_context: bool,
) -> PicoTutorConfidence:
    top_score = max(
        [
            lesson_matches[0].score if lesson_matches else 0,
            knowledge_matches[0].score if knowledge_matches else 0,
        ]
    )
    if risky or asked_for_more_context:
        return "low"
    if top_score >= 10:
        return "high"
    if top_score >= 6:
        return "medium"
    return "low"


def _smallest_decisive_signal(intent: PicoTutorIntent) -> str:
    prompts = {
        "choose": "What matters most here: memory/learning, channel breadth, isolation, or lightweight deployment?",
        "install": "Paste the exact install command you ran and the first failure output.",
        "repair": "Paste the first failing command or the shortest error/log excerpt that proves the failure.",
        "migrate": "Which stack are you moving from and what must keep working on day one?",
        "compare": "What matters more right now: setup speed, security isolation, channel ecosystem, or persistent memory?",
        "tailscale": "Run `tailscale status` and paste the output from both ends if possible.",
        "optimize": "What is the actual pain point: latency, memory growth, token spend, or uptime?",
        "integrate": "Which integration is failing: provider, gateway, channel, or callback?",
    }
    return prompts[intent]


def _build_steps(
    *,
    intent: PicoTutorIntent,
    lesson: LessonDoc | None,
    skill_level: PicoTutorSkillLevel,
    risky_keyword: str | None,
) -> list[str]:
    steps: list[str] = []
    if lesson:
        for step in lesson.steps[:3]:
            title = step.get("title", "Step")
            body = step.get("body", "")
            steps.append(f"{title}: {body}")
    else:
        steps.extend(
            [
                "Identify the failing layer before changing anything else.",
                "Make the smallest fix that matches the current layer.",
                "Re-run the exact verification step before branching into another fix.",
            ]
        )

    if intent == "tailscale":
        steps.insert(
            0,
            "Stay on private tailnet access first. Do not expose admin surfaces publicly unless there is a real requirement.",
        )
    if skill_level == "beginner":
        steps.append("Stop after the first successful verification. Do not optimize yet.")
    if risky_keyword:
        steps.append(
            f"Do not execute the {risky_keyword} action until the environment and rollback path are explicit."
        )
    return steps[:5]


def _build_commands(
    *,
    lesson: LessonDoc | None,
    knowledge_matches: list[RetrievalMatch],
    intent: PicoTutorIntent,
) -> list[PicoTutorCommand]:
    commands: list[PicoTutorCommand] = []
    if lesson:
        for index, step in enumerate(lesson.steps):
            command = step.get("command")
            if isinstance(command, str) and command.strip():
                commands.append(
                    PicoTutorCommand(
                        label=step.get("title", f"Lesson command {index + 1}"),
                        code=command,
                        language="bash",
                        note=step.get("note"),
                    )
                )

    docs_by_id = {doc.id: doc for doc in load_knowledge_docs()}
    for match in knowledge_matches:
        if match.kind != "knowledge_pack":
            continue
        doc = docs_by_id.get(match.id)
        if not doc:
            continue
        for command in doc.command_blocks:
            commands.append(command)

    if intent == "tailscale" and not commands:
        commands.extend(
            [
                PicoTutorCommand(
                    label="Check tailnet state", code="tailscale status", language="bash"
                ),
                PicoTutorCommand(
                    label="Check local tailnet IP", code="tailscale ip", language="bash"
                ),
            ]
        )

    deduped: list[PicoTutorCommand] = []
    seen: set[str] = set()
    for command in commands:
        if command.code not in seen:
            deduped.append(command)
            seen.add(command.code)
    return deduped[:4]


def _build_verify(lesson: LessonDoc | None, intent: PicoTutorIntent) -> list[str]:
    verify = [lesson.validation] if lesson else []
    if intent == "tailscale":
        verify.append(
            "Confirm you can reach the target over the tailnet without switching to public exposure."
        )
    if not verify:
        verify.append(
            "Run the exact command that was failing before. If the result changes, capture the new output."
        )
    return verify[:3]


def _build_if_this_fails(
    lesson: LessonDoc | None,
    *,
    intent: PicoTutorIntent,
    official_fetch_failed: bool,
) -> list[str]:
    items = list(lesson.troubleshooting[:3]) if lesson else []
    items.append(_smallest_decisive_signal(intent))
    if official_fetch_failed:
        items.append(
            "Official evidence could not be fetched live, so treat the guidance as grounded but not freshly verified."
        )
    deduped: list[str] = []
    for item in items:
        if item and item not in deduped:
            deduped.append(item)
    return deduped[:4]


def _build_sources(
    lesson_matches: list[RetrievalMatch],
    knowledge_matches: list[RetrievalMatch],
    official_evidence: list[OfficialEvidence],
) -> list[PicoTutorSource]:
    sources: list[PicoTutorSource] = []
    for match in lesson_matches[:2]:
        sources.append(
            PicoTutorSource(
                kind="lesson",
                title=match.title,
                sourcePath=match.source_path or match.id,
                href=match.href,
                excerpt=match.excerpt,
            )
        )
    for match in knowledge_matches[:2]:
        sources.append(
            PicoTutorSource(
                kind="knowledge_pack",
                title=match.title,
                sourcePath=match.source_path or match.id,
                excerpt=match.excerpt,
            )
        )
    for item in official_evidence[:2]:
        sources.append(
            PicoTutorSource(
                kind="official",
                title=item.title,
                sourcePath=urlparse(item.href).netloc,
                href=item.href,
                excerpt=item.excerpt,
            )
        )
    return sources


def _build_summary(
    *,
    question: str,
    lesson: LessonDoc | None,
    intent: PicoTutorIntent,
    setup_context: dict[str, Any] | None,
    risky_keyword: str | None,
) -> tuple[str, str, str]:
    runtime = (setup_context or {}).get("runtime") if isinstance(setup_context, dict) else None
    onboarding = (
        (setup_context or {}).get("onboarding") if isinstance(setup_context, dict) else None
    )
    runtime_status = runtime.get("status") if isinstance(runtime, dict) else None
    onboarding_step = onboarding.get("current_step") if isinstance(onboarding, dict) else None

    situation_parts = [f"Operator asks: {question.strip()}."]
    if lesson:
        situation_parts.append(f"Blocked lesson context: {lesson.title}.")
    if onboarding_step:
        situation_parts.append(f"Hosted onboarding is currently on `{onboarding_step}`.")
    if runtime_status:
        situation_parts.append(f"Runtime currently reports `{runtime_status}`.")

    if risky_keyword:
        diagnosis = f"This request touches `{risky_keyword}`, so the tutor should stop short of irreversible or exposure-creating defaults."
    elif lesson:
        diagnosis = f"The strongest grounded path is `{lesson.title}` because it matches the active lesson lane and its validation path."
    elif intent == "choose":
        diagnosis = "The question is a stack-selection problem. Hermes stays the default unless the constraints clearly favor another agent."
    elif intent == "tailscale":
        diagnosis = "This is primarily a remote-access problem. Private tailnet reachability is the safest first path."
    else:
        diagnosis = "This looks like a concrete operator task, so the shortest path is one fix plus one verification instead of branching."

    summary = " ".join(situation_parts + [diagnosis])
    return " ".join(situation_parts), diagnosis, summary


async def _generate_with_model(
    *,
    request: PicoTutorRequest,
    api_key: str | None,
    api_key_source: str,
    intent: PicoTutorIntent,
    skill_level: PicoTutorSkillLevel,
    retrieved_lessons: list[RetrievalMatch],
    retrieved_docs: list[RetrievalMatch],
    official_evidence: list[OfficialEvidence],
    fallback_reply: PicoTutorGuidance,
    entitlement: PicoTutorEntitlement,
) -> PicoTutorResponse | PicoTutorGenerationFailure:
    if not api_key:
        return PicoTutorGenerationFailure(
            status_code=status.HTTP_409_CONFLICT,
            code="TUTOR_PROVIDER_REQUIRED",
            message="No validated model provider is available for live Tutor.",
        )

    tracer = get_tracer()
    model_name = settings.pico_tutor_model.replace("openai/", "", 1)
    with tracer.start_as_current_span("mutx.pico.tutor.generate") as span:
        span.set_attribute("agent.id", "pico_tutor")
        span.set_attribute("intent", intent)
        span.set_attribute("skill_level", skill_level)
        span.set_attribute("llm.model", settings.pico_tutor_model)
        span.set_attribute("auth_source", api_key_source)
        try:
            client = AsyncOpenAI(api_key=api_key)
            prompt_payload = {
                "question": request.question,
                "lessonSlug": request.lessonSlug,
                "progress": request.progress,
                "setupContext": request.setupContext.model_dump() if request.setupContext else None,
                "intent": intent,
                "skillLevel": skill_level,
                "lessonMatches": [match.__dict__ for match in retrieved_lessons],
                "knowledgeMatches": [match.__dict__ for match in retrieved_docs],
                "officialEvidence": [item.__dict__ for item in official_evidence],
                "fallbackReply": fallback_reply.model_dump(),
            }
            response = await client.chat.completions.create(
                model=model_name,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"{load_system_prompt()}\n\n"
                            "Return JSON only. Keep the existing field names and preserve citations."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt_payload)},
                ],
            )
            content = response.choices[0].message.content or ""
            parsed = PicoTutorGuidance.model_validate_json(content)
            response_id = getattr(response, "id", None)
            if not isinstance(response_id, str) or not response_id.strip():
                raise ValueError("OpenAI response did not include a response identifier")
            if api_key_source not in {"user", "platform"}:
                raise ValueError("Tutor generation did not use a proven provider source")
            generated = PicoTutorResponse(
                **parsed.model_dump(),
                entitlement=entitlement,
                generation=PicoTutorGenerationProof(
                    source=api_key_source,
                    model=model_name,
                    responseId=response_id,
                    completedAt=datetime.now(timezone.utc).isoformat(),
                ),
            )
            span.set_attribute("citation_count", len(generated.structured.sources))
            span.set_attribute("answer.confidence", generated.confidence)
            span.set_attribute("llm.response_id", response_id)
            span.set_status(Status(StatusCode.OK))
            return generated
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            upstream_status = getattr(exc, "status_code", None)
            if upstream_status == status.HTTP_429_TOO_MANY_REQUESTS:
                logger.info("Pico tutor model rate limited: %s", exc)
                return PicoTutorGenerationFailure(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    code="TUTOR_RATE_LIMITED",
                    message="The Tutor model is rate limited. Wait a moment and try again.",
                )
            logger.warning("Pico tutor model generation failed: %s", exc)
            return PicoTutorGenerationFailure(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="TUTOR_MODEL_UNAVAILABLE",
                message="The Tutor model could not complete this request. Your Academy guidance is still available.",
            )


async def generate_pico_tutor_reply(
    request: PicoTutorRequest,
    *,
    db: AsyncSession | None = None,
    current_user: User | None = None,
    trace_id: str | None = None,
) -> PicoTutorResponse:
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Authentication is required."},
        )
    entitlement = require_pico_tutor_access(current_user)
    question = request.question.strip()
    lesson = get_lesson_by_slug(request.lessonSlug)
    intent = classify_intent(question, request.lessonSlug)
    skill_level = detect_skill_level(
        question,
        request.setupContext.model_dump() if request.setupContext else None,
    )
    risky_keyword = detect_risk(question)
    version_sensitive = is_version_sensitive(question)

    tracer = get_tracer()
    with tracer.start_as_current_span("mutx.pico.tutor.request") as span:
        span.set_attribute("agent.id", "pico_tutor")
        span.set_attribute("intent", intent)
        span.set_attribute("skill_level", skill_level)
        span.set_attribute("lesson.slug", request.lessonSlug or "")
        span.set_attribute("session.id", str(current_user.id) if current_user else "anonymous")
        if trace_id:
            span.set_attribute("trace.id", trace_id)

        api_key, api_key_source = await resolve_pico_tutor_api_key(
            db,
            user=current_user,
        )
        span.set_attribute("model_auth_source", api_key_source)
        if not api_key or api_key_source not in {"user", "platform"}:
            span.set_status(Status(StatusCode.ERROR, "Tutor provider unavailable"))
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "TUTOR_PROVIDER_REQUIRED",
                    "message": "No validated model provider is available for live Tutor.",
                    "canConnect": entitlement.byokAccess,
                },
            )
        with tracer.start_as_current_span("mutx.pico.tutor.retrieve") as retrieve_span:
            lesson_matches = retrieve_lessons(question, request.lessonSlug)
            knowledge_matches = retrieve_knowledge_docs(
                question,
                intent=intent,
                version_sensitive=version_sensitive,
            )
            source_mix = f"lesson:{len(lesson_matches)},knowledge_pack:{len(knowledge_matches)}"
            retrieve_span.set_attribute("source_mix", source_mix)

        official_links = collect_official_links(knowledge_matches, intent)
        official_evidence: list[OfficialEvidence] = []
        official_fetch_failed = False
        low_confidence_retrieval = (bool(lesson_matches) and lesson_matches[0].score < 6) or (
            bool(knowledge_matches) and knowledge_matches[0].score < 6
        )
        used_official_fallback = bool(version_sensitive or low_confidence_retrieval)
        if used_official_fallback and official_links:
            with tracer.start_as_current_span("mutx.pico.tutor.fallback") as fallback_span:
                fallback_span.set_attribute("used_official_fallback", True)
                for link in official_links[:2]:
                    try:
                        evidence = await fetch_official_evidence(link)
                        if evidence:
                            official_evidence.append(evidence)
                    except Exception as exc:
                        official_fetch_failed = True
                        logger.info("Official evidence fetch failed for %s: %s", link, exc)
                fallback_span.set_attribute("official_result_count", len(official_evidence))

        asked_for_more_context = len(_tokenize(question)) < 4
        situation, diagnosis, summary = _build_summary(
            question=question,
            lesson=lesson,
            intent=intent,
            setup_context=request.setupContext.model_dump() if request.setupContext else None,
            risky_keyword=risky_keyword,
        )
        steps = _build_steps(
            intent=intent,
            lesson=lesson,
            skill_level=skill_level,
            risky_keyword=risky_keyword,
        )
        commands = _build_commands(
            lesson=lesson, knowledge_matches=knowledge_matches, intent=intent
        )
        verify = _build_verify(lesson, intent)
        if_this_fails = _build_if_this_fails(
            lesson,
            intent=intent,
            official_fetch_failed=official_fetch_failed,
        )
        sources = _build_sources(lesson_matches, knowledge_matches, official_evidence)
        if not sources:
            sources = [
                PicoTutorSource(
                    kind="knowledge_pack",
                    title="TROUBLESHOOTING_FLOW",
                    sourcePath="knowledge/pico_ops/TROUBLESHOOTING_FLOW.md",
                    excerpt="Diagnose the failing layer before proposing fixes.",
                )
            ]

        lesson_links = [
            PicoTutorLessonLink(
                id=match.id, title=match.title, href=match.href or f"/pico/academy/{match.id}"
            )
            for match in lesson_matches
        ]
        doc_links = [
            PicoTutorDocLink(label="Support lane", href="/pico/support", sourcePath="pico/support"),
            *[
                PicoTutorDocLink(
                    label=urlparse(item.href).netloc.replace("www.", "") or item.title,
                    href=item.href,
                    sourcePath=urlparse(item.href).netloc,
                )
                for item in official_evidence
            ],
        ]
        if not official_evidence:
            for link in official_links[:2]:
                doc_links.append(
                    PicoTutorDocLink(
                        label=urlparse(link).netloc.replace("www.", "") or "official docs",
                        href=link,
                        sourcePath=urlparse(link).netloc,
                    )
                )

        confidence = _confidence_from_scores(
            lesson_matches,
            knowledge_matches,
            risky=bool(risky_keyword),
            asked_for_more_context=asked_for_more_context,
        )
        next_question = _smallest_decisive_signal(intent) if confidence == "low" else None
        escalation_reason = None
        if risky_keyword:
            escalation_reason = f"High-risk topic detected around `{risky_keyword}`. Do not proceed without a deliberate rollback or approval path."
        elif confidence == "low":
            escalation_reason = "Evidence is thin. Ask for the smallest decisive signal before changing more of the system."

        fallback_reply = PicoTutorGuidance(
            title=(
                lesson.title
                if lesson
                else (lesson_matches[0].title if lesson_matches else "Pico Tutor")
            ),
            summary=summary,
            answer=f"{diagnosis} {_build_verify(lesson, intent)[0]}",
            confidence=confidence,
            nextActions=steps[:3],
            lessons=lesson_links,
            docs=doc_links[:4],
            recommendedLessonIds=[item.id for item in lesson_links],
            escalate=bool(escalation_reason),
            escalationReason=escalation_reason,
            structured=PicoTutorStructuredReply(
                situation=situation,
                diagnosis=diagnosis,
                steps=steps,
                commands=commands,
                verify=verify,
                ifThisFails=if_this_fails,
                officialLinks=doc_links[1:4] if len(doc_links) > 1 else [],
                sources=sources,
                nextQuestion=next_question,
            ),
            intent=intent,
            skillLevel=skill_level,
            usedOfficialFallback=used_official_fallback,
        )

        generated_reply = await _generate_with_model(
            request=request,
            api_key=api_key,
            api_key_source=api_key_source,
            intent=intent,
            skill_level=skill_level,
            retrieved_lessons=lesson_matches,
            retrieved_docs=knowledge_matches,
            official_evidence=official_evidence,
            fallback_reply=fallback_reply,
            entitlement=entitlement,
        )
        if isinstance(generated_reply, PicoTutorGenerationFailure):
            span.set_status(Status(StatusCode.ERROR, generated_reply.message))
            raise HTTPException(
                status_code=generated_reply.status_code,
                detail={
                    "code": generated_reply.code,
                    "message": generated_reply.message,
                    "retryable": generated_reply.status_code in {429, 503},
                },
            )
        final_reply = generated_reply
        span.set_attribute("used_official_fallback", final_reply.usedOfficialFallback)
        span.set_attribute("citation_count", len(final_reply.structured.sources))
        span.set_attribute("answer.confidence", final_reply.confidence)
        span.set_status(Status(StatusCode.OK))
        return final_reply
