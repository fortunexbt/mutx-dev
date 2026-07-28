"""
MutxPolicyClient — SDK client for watching and reloading policies.
"""

import asyncio
import logging

import httpx

from mutx._http import api_path, normalize_api_base_url

logger = logging.getLogger(__name__)


DEFAULT_GUARDRAIL_PROFILES: dict[str, list[str]] = {
    "strict": ["pii_block", "toxicity_check"],
    "standard": ["pii_block"],
    "permissive": [],
}


class Rule:
    """Rule model matching the server-side Rule schema."""

    def __init__(
        self,
        *,
        type: str,  # "block" | "allow" | "warn"
        pattern: str,
        action: str,
        scope: str,  # "input" | "output" | "tool"
    ):
        self.type = type
        self.pattern = pattern
        self.action = action
        self.scope = scope

    def __repr__(self) -> str:
        return f"Rule(type={self.type!r}, pattern={self.pattern!r}, scope={self.scope!r})"

    @classmethod
    def from_dict(cls, data: dict) -> "Rule":
        return cls(**data)


class MutxPolicyClient:
    """
    Client for polling and hot-reloading a policy from the mutx API.

    Parameters
    ----------
    api_url : str
        Base URL of the mutx API (e.g. "https://api.mutx.dev").
    policy_name : str
        Name of the policy to watch.
    api_key : str
        Bearer token for authentication.
    """

    def __init__(
        self,
        api_url: str,
        policy_name: str,
        api_key: str,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_base_url = normalize_api_base_url(api_url)
        self.policy_name = policy_name
        self._api_key = api_key
        self._http = httpx.Client(
            base_url=self.api_base_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=30.0,
        )
        self._watch_task: asyncio.Task[None] | None = None
        self._cancel_event: asyncio.Event | None = None
        self._current_policy: dict | None = None
        self._current_version: int | None = None
        self._guardrail_profiles: dict[str, list[str]] = dict(DEFAULT_GUARDRAIL_PROFILES)

    @property
    def guardrail_profiles(self) -> dict[str, list[str]]:
        return self._guardrail_profiles

    def get_guardrail_profile(self, profile_name: str) -> list[str]:
        return self._guardrail_profiles.get(profile_name, [])

    def set_guardrail_profile(self, profile_name: str, rules: list[str]) -> None:
        self._guardrail_profiles[profile_name] = rules

    def load_guardrail_profiles(self) -> dict[str, list[str]]:
        if self._current_policy is not None:
            profiles = self._current_policy.get("guardrail_profiles")
            if profiles:
                self._guardrail_profiles = profiles
        return self._guardrail_profiles

    # ------------------------------------------------------------------
    # Watch lifecycle
    # ------------------------------------------------------------------

    def start_watching(self, poll_interval: int = 30) -> None:
        """
        Start background polling of /v1/policies/{name}.

        When the server-side version changes, ``_current_policy`` is
        updated and subclasses can override ``on_policy_changed`` to react.
        """
        if self._watch_task is not None:
            logger.warning("start_watching called but a watch is already running")
            return

        self._cancel_event = asyncio.Event()
        self._watch_task = asyncio.create_task(self._poll_loop(poll_interval))
        logger.info("Policy watch started for '%s' (interval=%ds)", self.policy_name, poll_interval)

    async def stop_watching(self) -> None:
        """Cancel the background polling task."""
        if self._watch_task is None:
            return

        if self._cancel_event is not None:
            self._cancel_event.set()

        await self._watch_task
        self._watch_task = None
        self._cancel_event = None
        logger.info("Policy watch stopped for '%s'", self.policy_name)

    def stop(self) -> None:
        """Synchronous alias for stop_watching (for use in finally blocks)."""
        if self._watch_task is not None:
            try:
                asyncio.get_event_loop().run_until_complete(self.stop_watching())
            except RuntimeError:
                pass

    # ------------------------------------------------------------------
    # Policy access
    # ------------------------------------------------------------------

    def get_rules(self, scope: str) -> list[Rule]:
        """
        Return all rules for the given scope in the current policy.
        Returns empty list if no policy is loaded yet.
        """
        if self._current_policy is None:
            return []
        return [
            Rule.from_dict(r)
            for r in self._current_policy.get("rules", [])
            if r.get("scope") == scope
        ]

    @property
    def current_version(self) -> int | None:
        """The last known server-side policy version."""
        return self._current_version

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _poll_loop(self, poll_interval: int) -> None:
        cancel = self._cancel_event
        assert cancel is not None

        # Initial fetch
        await self._fetch_and_update()

        while not cancel.is_set():
            try:
                await asyncio.wait_for(cancel.wait(), timeout=poll_interval)
                break  # cancelled
            except asyncio.TimeoutError:
                await self._fetch_and_update()

    async def _fetch_and_update(self) -> None:
        try:
            resp = self._http.get(api_path("policies/{policy_name}", policy_name=self.policy_name))
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("Failed to fetch policy '%s': %s", self.policy_name, exc)
            return

        version = data.get("version")
        if version is None:
            return

        if version != self._current_version:
            self._current_version = version
            self._current_policy = data
            self.on_policy_changed(data)
            logger.info(
                "Policy '%s' updated to version %s (triggering %d rules)",
                self.policy_name,
                version,
                len(data.get("rules", [])),
            )

    def on_policy_changed(self, policy_data: dict) -> None:
        """
        Called when the policy version changes.
        Default implementation auto-loads guardrail profiles if present.
        """
        self.load_guardrail_profiles()


__all__ = ["MutxPolicyClient", "Rule", "DEFAULT_GUARDRAIL_PROFILES"]
