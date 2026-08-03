import pytest

from cloud_steward.datahub import DataHubContextProvider
from cloud_steward.models import PlanRequest, RiskLevel
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
