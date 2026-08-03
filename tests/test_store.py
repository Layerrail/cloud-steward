from cloud_steward.datahub import DataHubContextProvider
from cloud_steward.memory import PlanStore
from cloud_steward.models import ApprovalRequest, PlanRequest
from cloud_steward.planner import PlanGenerator
from cloud_steward.settings import Settings


def test_plan_store_persists_context_and_named_approval(tmp_path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'plans.db'}")
    store = PlanStore(settings.database_url)
    request = PlanRequest(goal="Inspect billing health before scaling", context_query="billing")
    context = DataHubContextProvider._sample(request.context_query)
    plan = PlanGenerator._deterministic_plan(request, context)

    store.save(request, context, plan)
    approved = store.approve(
        str(plan.id),
        ApprovalRequest(approved_by="test-reviewer", note="Scope reviewed"),
    )

    assert approved is not None
    assert approved["status"] == "approved"
    assert approved["approved_by"] == "test-reviewer"
    assert approved["context"]["provider"] == "sample-datahub-context"

    results = store.search_similar("Inspect billing health before scaling")
    assert results[0]["plan_id"] == str(plan.id)
    assert results[0]["provider"] == "local-deterministic-fallback"
