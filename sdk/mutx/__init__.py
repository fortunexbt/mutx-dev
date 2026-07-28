import httpx

from mutx._http import DEFAULT_BASE_URL, normalize_api_base_url
from mutx.agent_runtime import (
    AgentInfo as AgentInfo,
)
from mutx.agent_runtime import (
    AgentMetrics as AgentMetrics,
)
from mutx.agent_runtime import (
    Command as Command,
)
from mutx.agent_runtime import (
    MutxAgentClient as MutxAgentClient,
)
from mutx.agent_runtime import (
    MutxAgentSyncClient as MutxAgentSyncClient,
)
from mutx.agent_runtime import (
    create_agent_client as create_agent_client,
)
from mutx.agents import Agents
from mutx.analytics import Analytics
from mutx.api_keys import APIKeys
from mutx.approvals import Approvals as Approvals
from mutx.assistant import Assistant
from mutx.budgets import Budgets
from mutx.clawhub import ClawHub
from mutx.deployments import Deployments
from mutx.governance_credentials import GovernanceCredentials
from mutx.governance_supervision import GovernanceSupervision
from mutx.ingest import Ingest
from mutx.leads import Contacts as Contacts
from mutx.leads import Leads
from mutx.newsletter import Newsletter
from mutx.observability import Observability
from mutx.onboarding import Onboarding
from mutx.pagination import Page as Page
from mutx.pagination import PageEnvelopeError as PageEnvelopeError
from mutx.runtime import Runtime
from mutx.scheduler import Scheduler
from mutx.security import Security
from mutx.sessions import Sessions
from mutx.swarms import Swarms
from mutx.templates import Templates
from mutx.usage import UsageEvents
from mutx.webhooks import Webhooks


class MutxClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.api_base_url = normalize_api_base_url(base_url)
        self.timeout = timeout
        self.http = httpx.Client(
            base_url=self.api_base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=timeout,
        )

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> "MutxClient":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    @property
    def agents(self) -> Agents:
        return Agents(self.http)

    @property
    def analytics(self) -> Analytics:
        return Analytics(self.http)

    @property
    def api_keys(self) -> APIKeys:
        return APIKeys(self.http)

    @property
    def approvals(self) -> Approvals:
        return Approvals(self.http)

    @property
    def assistant(self) -> Assistant:
        return Assistant(self.http)

    @property
    def budgets(self) -> Budgets:
        return Budgets(self.http)

    @property
    def clawhub(self) -> ClawHub:
        return ClawHub(self.http)

    @property
    def deployments(self) -> Deployments:
        return Deployments(self.http)

    @property
    def governance_credentials(self) -> GovernanceCredentials:
        return GovernanceCredentials(self.http)

    @property
    def governance_supervision(self) -> GovernanceSupervision:
        return GovernanceSupervision(self.http)

    @property
    def ingest(self) -> Ingest:
        return Ingest(self.http)

    @property
    def leads(self) -> Leads:
        return Leads(self.http)

    @property
    def newsletter(self) -> Newsletter:
        return Newsletter(self.http)

    @property
    def observability(self) -> Observability:
        return Observability(self.http)

    @property
    def onboarding(self) -> Onboarding:
        return Onboarding(self.http)

    @property
    def runtime(self) -> Runtime:
        return Runtime(self.http)

    @property
    def scheduler(self) -> Scheduler:
        return Scheduler(self.http)

    @property
    def security(self) -> Security:
        return Security(self.http)

    @property
    def sessions(self) -> Sessions:
        return Sessions(self.http)

    @property
    def swarms(self) -> Swarms:
        return Swarms(self.http)

    @property
    def templates(self) -> Templates:
        return Templates(self.http)

    @property
    def usage(self) -> UsageEvents:
        return UsageEvents(self.http)

    @property
    def webhooks(self) -> Webhooks:
        return Webhooks(self.http)
