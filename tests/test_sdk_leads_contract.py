"""
SDK contract tests for leads module.
Tests verify that the SDK correctly maps to the backend API contract.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any

import httpx
import pytest

from mutx.leads import Contacts, Lead, Leads


def _lead_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": str(uuid.uuid4()),
        "email": "test@example.com",
        "name": "Test User",
        "company": "Test Corp",
        "message": "Hello",
        "source": "web",
        "created_at": "2026-03-12T09:00:00",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Lead model tests
# ---------------------------------------------------------------------------


def test_lead_parses_required_fields() -> None:
    lead = Lead(_lead_payload())

    assert isinstance(lead.id, uuid.UUID)
    assert lead.email == "test@example.com"
    assert lead.name == "Test User"
    assert lead.company == "Test Corp"
    assert lead.message == "Hello"
    assert lead.source == "web"
    assert isinstance(lead.created_at, datetime)


def test_lead_parses_optional_fields() -> None:
    lead = Lead(
        _lead_payload(
            name=None,
            company=None,
            message=None,
            source=None,
        )
    )

    assert lead.name is None
    assert lead.company is None
    assert lead.message is None
    assert lead.source is None


def test_lead_repr() -> None:
    lead = Lead(_lead_payload())
    assert "Lead(id=" in repr(lead)
    assert "test@example.com" in repr(lead)


# ---------------------------------------------------------------------------
# Leads.create
# ---------------------------------------------------------------------------


def test_leads_create_hits_contract_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(201, json=_lead_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    leads = Leads(client)

    leads.create(email="alice@example.com", name="Alice", company="Acme", source="newsletter")

    assert captured["path"] == "/v1/leads"
    assert captured["method"] == "POST"
    assert captured["json"]["email"] == "alice@example.com"
    assert captured["json"]["name"] == "Alice"
    assert captured["json"]["company"] == "Acme"
    assert captured["json"]["source"] == "newsletter"


def test_leads_create_returns_lead() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json=_lead_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    leads = Leads(client)

    result = leads.create(email="test@example.com")

    assert isinstance(result, Lead)
    assert result.email == "test@example.com"


def test_leads_acreate_hits_contract_route() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(201, json=_lead_payload())

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    leads = Leads(client)

    asyncio.run(leads.acreate(email="bob@example.com", name="Bob"))

    assert captured["path"] == "/v1/leads"
    assert captured["method"] == "POST"
    assert captured["json"]["email"] == "bob@example.com"
    assert captured["json"]["name"] == "Bob"


def test_leads_acreate_returns_lead() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json=_lead_payload())

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    leads = Leads(client)

    result = asyncio.run(leads.acreate(email="test@example.com"))

    assert isinstance(result, Lead)
    assert result.email == "test@example.com"


# ---------------------------------------------------------------------------
# Leads.list
# ---------------------------------------------------------------------------


def test_leads_list_hits_contract_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "items": [_lead_payload(), _lead_payload(id=str(uuid.uuid4()))],
                "total": 2,
                "skip": 0,
                "limit": 50,
                "has_more": False,
            },
        )

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    leads = Leads(client)

    leads.list(skip=10, limit=25)

    assert captured["path"] == "/v1/leads"
    assert captured["method"] == "GET"
    assert captured["params"]["skip"] == "10"
    assert captured["params"]["limit"] == "25"


def test_leads_list_returns_list_of_leads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [_lead_payload(), _lead_payload(id=str(uuid.uuid4()))],
                "total": 2,
                "skip": 0,
                "limit": 50,
                "has_more": False,
            },
        )

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    leads = Leads(client)

    result = leads.list()

    assert isinstance(result, list)
    assert all(isinstance(lead, Lead) for lead in result)
    assert len(result) == 2


def test_leads_alist_hits_contract_route() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={"items": [], "total": 0, "skip": 0, "limit": 50, "has_more": False},
        )

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    leads = Leads(client)

    asyncio.run(leads.alist(skip=5, limit=20))

    assert captured["path"] == "/v1/leads"
    assert captured["method"] == "GET"
    assert captured["params"]["skip"] == "5"
    assert captured["params"]["limit"] == "20"


def test_leads_alist_returns_list_of_leads() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [_lead_payload()],
                "total": 1,
                "skip": 0,
                "limit": 50,
                "has_more": False,
            },
        )

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    leads = Leads(client)

    result = asyncio.run(leads.alist())

    assert isinstance(result, list)
    assert all(isinstance(lead, Lead) for lead in result)


# ---------------------------------------------------------------------------
# Leads.get
# ---------------------------------------------------------------------------


def test_leads_get_hits_contract_route() -> None:
    captured: dict[str, Any] = {}
    lead_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json=_lead_payload(id=str(lead_id)))

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    leads = Leads(client)

    leads.get(lead_id)

    assert captured["path"] == f"/v1/leads/{lead_id}"
    assert captured["method"] == "GET"


def test_leads_get_accepts_string_id() -> None:
    captured: dict[str, Any] = {}
    lead_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=_lead_payload(id=lead_id))

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    leads = Leads(client)

    result = leads.get(lead_id)

    assert isinstance(result, Lead)
    assert str(result.id) == lead_id


def test_leads_aget_hits_contract_route() -> None:
    captured: dict[str, Any] = {}
    lead_id = uuid.uuid4()

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json=_lead_payload(id=str(lead_id)))

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    leads = Leads(client)

    asyncio.run(leads.aget(lead_id))

    assert captured["path"] == f"/v1/leads/{lead_id}"
    assert captured["method"] == "GET"


# ---------------------------------------------------------------------------
# Leads.update
# ---------------------------------------------------------------------------


def test_leads_update_hits_contract_route() -> None:
    captured: dict[str, Any] = {}
    lead_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_lead_payload(id=str(lead_id), name="Updated"))

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    leads = Leads(client)

    leads.update(lead_id, name="Updated", company="NewCo")

    assert captured["path"] == f"/v1/leads/{lead_id}"
    assert captured["method"] == "PATCH"
    assert captured["json"]["name"] == "Updated"
    assert captured["json"]["company"] == "NewCo"


def test_leads_update_omits_none_fields() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_lead_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    leads = Leads(client)

    leads.update(uuid.uuid4(), name=None)

    assert "name" not in captured["json"]


def test_leads_update_returns_lead() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_lead_payload(name="Updated"))

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    leads = Leads(client)

    result = leads.update(uuid.uuid4(), name="Updated")

    assert isinstance(result, Lead)


def test_leads_aupdate_hits_contract_route() -> None:
    captured: dict[str, Any] = {}
    lead_id = uuid.uuid4()

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_lead_payload(id=str(lead_id)))

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    leads = Leads(client)

    asyncio.run(leads.aupdate(lead_id, source="updated_source"))

    assert captured["path"] == f"/v1/leads/{lead_id}"
    assert captured["method"] == "PATCH"
    assert captured["json"]["source"] == "updated_source"


# ---------------------------------------------------------------------------
# Leads.delete
# ---------------------------------------------------------------------------


def test_leads_delete_hits_contract_route() -> None:
    captured: dict[str, Any] = {}
    lead_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(204)

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    leads = Leads(client)

    leads.delete(lead_id)

    assert captured["path"] == f"/v1/leads/{lead_id}"
    assert captured["method"] == "DELETE"


def test_leads_adelete_hits_contract_route() -> None:
    captured: dict[str, Any] = {}
    lead_id = uuid.uuid4()

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(204)

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    leads = Leads(client)

    asyncio.run(leads.adelete(lead_id))

    assert captured["path"] == f"/v1/leads/{lead_id}"
    assert captured["method"] == "DELETE"


# ---------------------------------------------------------------------------
# Client type enforcement
# ---------------------------------------------------------------------------


def test_leads_sync_methods_reject_async_client() -> None:
    client = httpx.AsyncClient(base_url="https://api.test/v1/")
    leads = Leads(client)

    with pytest.raises(RuntimeError, match="requires a sync httpx.Client"):
        leads.create(email="test@example.com")

    with pytest.raises(RuntimeError, match="requires a sync httpx.Client"):
        leads.list()

    with pytest.raises(RuntimeError, match="requires a sync httpx.Client"):
        leads.get(uuid.uuid4())

    with pytest.raises(RuntimeError, match="requires a sync httpx.Client"):
        leads.update(uuid.uuid4())

    with pytest.raises(RuntimeError, match="requires a sync httpx.Client"):
        leads.delete(uuid.uuid4())


def test_leads_async_methods_reject_sync_client() -> None:
    """Async methods raise when awaited with a sync client (the check is inside the coroutine)."""
    client = httpx.Client(base_url="https://api.test/v1/")
    leads = Leads(client)

    with pytest.raises(RuntimeError, match="requires an async httpx.AsyncClient"):
        asyncio.run(leads.acreate(email="test@example.com"))

    with pytest.raises(RuntimeError, match="requires an async httpx.AsyncClient"):
        asyncio.run(leads.alist())

    with pytest.raises(RuntimeError, match="requires an async httpx.AsyncClient"):
        asyncio.run(leads.aget(uuid.uuid4()))

    with pytest.raises(RuntimeError, match="requires an async httpx.AsyncClient"):
        asyncio.run(leads.aupdate(uuid.uuid4()))

    with pytest.raises(RuntimeError, match="requires an async httpx.AsyncClient"):
        asyncio.run(leads.adelete(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Contacts — all methods hit /v1/leads/contacts routes
# ---------------------------------------------------------------------------


def test_contacts_create_hits_contacts_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(201, json=_lead_payload())

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    contacts = Contacts(client)

    contacts.create(email="contact@example.com", name="Contact")

    assert captured["path"] == "/v1/leads/contacts"
    assert captured["method"] == "POST"


def test_contacts_acreate_hits_contacts_route() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(201, json=_lead_payload())

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    contacts = Contacts(client)

    asyncio.run(contacts.acreate(email="contact@example.com"))

    assert captured["path"] == "/v1/leads/contacts"
    assert captured["method"] == "POST"


def test_contacts_list_hits_contacts_route() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(
            200,
            json={"items": [], "total": 0, "skip": 0, "limit": 50, "has_more": False},
        )

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    contacts = Contacts(client)

    contacts.list()

    assert captured["path"] == "/v1/leads/contacts"
    assert captured["method"] == "GET"


def test_contacts_alist_hits_contacts_route() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(
            200,
            json={"items": [], "total": 0, "skip": 0, "limit": 50, "has_more": False},
        )

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    contacts = Contacts(client)

    asyncio.run(contacts.alist())

    assert captured["path"] == "/v1/leads/contacts"
    assert captured["method"] == "GET"


def test_contacts_get_hits_contacts_route() -> None:
    captured: dict[str, Any] = {}
    contact_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json=_lead_payload(id=str(contact_id)))

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    contacts = Contacts(client)

    contacts.get(contact_id)

    assert captured["path"] == f"/v1/leads/contacts/{contact_id}"
    assert captured["method"] == "GET"


def test_contacts_aget_hits_contacts_route() -> None:
    captured: dict[str, Any] = {}
    contact_id = uuid.uuid4()

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json=_lead_payload(id=str(contact_id)))

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    contacts = Contacts(client)

    asyncio.run(contacts.aget(contact_id))

    assert captured["path"] == f"/v1/leads/contacts/{contact_id}"
    assert captured["method"] == "GET"


def test_contacts_update_hits_contacts_route() -> None:
    captured: dict[str, Any] = {}
    contact_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_lead_payload(id=str(contact_id)))

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    contacts = Contacts(client)

    contacts.update(contact_id, name="Updated Contact")

    assert captured["path"] == f"/v1/leads/contacts/{contact_id}"
    assert captured["method"] == "PATCH"
    assert captured["json"]["name"] == "Updated Contact"


def test_contacts_aupdate_hits_contacts_route() -> None:
    captured: dict[str, Any] = {}
    contact_id = uuid.uuid4()

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(200, json=_lead_payload(id=str(contact_id)))

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    contacts = Contacts(client)

    asyncio.run(contacts.aupdate(contact_id, company="NewCompany"))

    assert captured["path"] == f"/v1/leads/contacts/{contact_id}"
    assert captured["method"] == "PATCH"


def test_contacts_delete_hits_contacts_route() -> None:
    captured: dict[str, Any] = {}
    contact_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(204)

    client = httpx.Client(base_url="https://api.test/v1/", transport=httpx.MockTransport(handler))
    contacts = Contacts(client)

    contacts.delete(contact_id)

    assert captured["path"] == f"/v1/leads/contacts/{contact_id}"
    assert captured["method"] == "DELETE"


def test_contacts_adelete_hits_contacts_route() -> None:
    captured: dict[str, Any] = {}
    contact_id = uuid.uuid4()

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["method"] = request.method
        return httpx.Response(204)

    client = httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )
    contacts = Contacts(client)

    asyncio.run(contacts.adelete(contact_id))

    assert captured["path"] == f"/v1/leads/contacts/{contact_id}"
    assert captured["method"] == "DELETE"
