from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from cloud_steward.datahub import DataHubContextProvider
from cloud_steward.models import ActionPlan, PlanRequest, ProposedAction, RiskLevel
from cloud_steward.planner import PlanGenerator
from cloud_steward.settings import Settings


@pytest.mark.asyncio
async def test_deterministic_plan_is_dry_run_and_approval_first() -> None:
    settings = Settings(gemini_api_key=None, datahub_mcp_url=None, datahub_gms_url=None)
    request = PlanRequest(
        goal="Reduce checkout latency without breaking invoices",
        context_query="checkout invoice production",
    )
    context = await DataHubContextProvider(settings).collect(request.context_query)

    plan = await PlanGenerator(settings).generate(request, context)

    assert plan.requires_approval is True
    assert plan.overall_risk == RiskLevel.high
    assert any(action.mutation for action in plan.actions)
    assert all(action.rollback for action in plan.actions)
    assert all(action.verification for action in plan.actions)
    assert "no infrastructure mutation has executed" in " ".join(plan.assumptions).lower()


@pytest.mark.asyncio
async def test_sample_context_is_explicitly_disclosed() -> None:
    settings = Settings(datahub_mcp_url=None, datahub_gms_url=None)

    context = await DataHubContextProvider(settings).collect("billing")

    assert context.provider == "sample-datahub-context"
    assert "Demo context" in context.raw_excerpt
    assert context.resources


def test_guardrails_raise_mutating_plan_risk() -> None:
    plan = ActionPlan(
        goal="Scale a service",
        summary="Proposed scaling plan",
        actions=[
            ProposedAction(
                order=1,
                action="Scale service",
                target="production-api",
                reason="Reduce saturation",
                expected_result="Lower queue depth",
                verification="Compare queue depth and errors",
                rollback="Restore prior replica count",
                risk=RiskLevel.low,
                mutation=True,
            )
        ],
        overall_risk=RiskLevel.low,
        requires_approval=False,
    )

    guarded = PlanGenerator.enforce_guardrails(plan)

    assert guarded.requires_approval is True
    assert guarded.actions[0].risk == RiskLevel.high
    assert guarded.overall_risk == RiskLevel.high


def test_datahub_payload_preserves_governance_and_lineage() -> None:
    urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,commerce.orders,PROD)"
    resources = DataHubContextProvider._resources_from_payload(
        {
            "searchResults": [
                {"entity": {"urn": urn, "properties": {"name": "orders"}}}
            ]
        }
    )
    details = DataHubContextProvider._resources_from_payload(
        DataHubContextProvider._unwrap_result(
            {
                "result": [
                    {
                        "urn": urn,
                        "type": "DATASET",
                        "properties": {
                            "name": "orders",
                            "description": "Checkout orders",
                        },
                        "ownership": {
                            "owners": [
                                {
                                    "owner": {
                                        "urn": "urn:li:corpGroup:commerce-platform",
                                        "properties": {
                                            "displayName": "Commerce Platform"
                                        },
                                    }
                                }
                            ]
                        },
                        "tags": {
                            "tags": [
                                {"tag": {"properties": {"name": "customer-facing"}}}
                            ]
                        },
                        "glossaryTerms": {
                            "terms": [
                                {"term": {"properties": {"name": "PII"}}}
                            ]
                        },
                        "structuredProperties": {
                            "properties": [
                                {
                                    "structuredProperty": {
                                        "definition": {
                                            "displayName": "Data Quality Score"
                                        }
                                    },
                                    "values": [{"numberValue": 98.5}],
                                }
                            ]
                        },
                        "health": [{"type": "INCIDENTS", "status": "PASS"}],
                    }
                ]
            }
        )
    )
    resources = DataHubContextProvider._merge_resources(resources, details)
    DataHubContextProvider._apply_lineage(
        resources,
        urn,
        {
            "downstreams": {
                "searchResults": [
                    {
                        "entity": {
                            "urn": (
                                "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
                                "finance.invoices,PROD)"
                            ),
                            "properties": {"name": "invoices"},
                        }
                    }
                ]
            }
        },
        upstream=False,
    )

    assert resources[0].owner == "Commerce Platform"
    assert resources[0].environment == "PROD"
    assert resources[0].tags == ["customer-facing"]
    assert resources[0].downstream == ["invoices"]
    assert "Glossary terms: PII" in resources[0].evidence
    assert "Data Quality Score: 98.5" in resources[0].evidence
    assert "INCIDENTS: PASS" in resources[0].evidence


def test_datahub_plain_query_uses_structured_keyword_search() -> None:
    tool = type(
        "SearchTool",
        (),
        {
            "name": "search",
            "inputSchema": {
                "properties": {"query": {"type": "string"}, "num_results": {"type": "integer"}}
            },
        },
    )()

    arguments = DataHubContextProvider._arguments_for(tool, "checkout invoice")

    assert arguments == {"query": "/q checkout OR invoice", "num_results": 8}


@pytest.mark.asyncio
async def test_live_datahub_collection_enriches_search_results() -> None:
    urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,commerce.orders,PROD)"

    class FakeSession:
        def __init__(self) -> None:
            self.calls = []

        async def list_tools(self):
            return SimpleNamespace(
                tools=[
                    SimpleNamespace(
                        name="search",
                        inputSchema={
                            "properties": {
                                "query": {"type": "string"},
                                "num_results": {"type": "integer"},
                            }
                        },
                    ),
                    SimpleNamespace(name="get_entities", inputSchema={}),
                    SimpleNamespace(name="get_lineage", inputSchema={}),
                ]
            )

        async def call_tool(self, name, arguments):
            self.calls.append((name, arguments))
            if name == "search":
                payload = {
                    "searchResults": [
                        {"entity": {"urn": urn, "properties": {"name": "orders"}}}
                    ]
                }
            elif name == "get_entities":
                payload = {
                    "result": [
                        {
                            "urn": urn,
                            "type": "DATASET",
                            "properties": {"name": "orders"},
                            "ownership": {
                                "owners": [
                                    {
                                        "owner": {
                                            "properties": {
                                                "displayName": "Commerce Platform"
                                            }
                                        }
                                    }
                                ]
                            },
                        }
                    ]
                }
            else:
                direction = "upstreams" if arguments["upstream"] else "downstreams"
                related = "raw_orders" if arguments["upstream"] else "revenue_dashboard"
                payload = {
                    direction: {
                        "searchResults": [
                            {
                                "entity": {
                                    "urn": (
                                        "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
                                        f"commerce.{related},PROD)"
                                    ),
                                    "type": "DATASET",
                                    "properties": {"name": related},
                                }
                            }
                        ]
                    }
                }
            return SimpleNamespace(structuredContent=payload, content=[])

    fake_session = FakeSession()

    @asynccontextmanager
    async def session():
        yield fake_session

    provider = DataHubContextProvider(Settings(datahub_gms_url="http://datahub:8080"))
    provider._session = session

    snapshot = await provider.collect("revenue orders")

    assert snapshot.provider == "datahub-mcp"
    assert provider.runtime_mode == "live"
    assert snapshot.resources[0].owner == "Commerce Platform"
    assert snapshot.resources[0].upstream == ["raw_orders"]
    assert snapshot.resources[0].downstream == ["revenue_dashboard"]
    assert [call[0] for call in fake_session.calls] == [
        "search",
        "get_entities",
        "get_lineage",
        "get_lineage",
    ]

    plan = await PlanGenerator(Settings()).generate(
        PlanRequest(goal="Protect revenue reporting", context_query="revenue orders"),
        snapshot,
    )
    assert plan.context_findings[0] == (
        "Live DataHub MCP context was collected with read-only tools: "
        "search, get_entities, get_lineage."
    )
