from cloud_steward.datahub import DataHubContextProvider
from cloud_steward.memory import PlanStore
from cloud_steward.models import ActionPlan, ApprovalRequest, PlanRequest
from cloud_steward.planner import PlanGenerator


class StewardService:
    def __init__(
        self,
        context_provider: DataHubContextProvider,
        planner: PlanGenerator,
        store: PlanStore,
    ):
        self.context_provider = context_provider
        self.planner = planner
        self.store = store

    async def propose(self, request: PlanRequest) -> ActionPlan:
        context = await self.context_provider.collect(request.context_query)
        plan = await self.planner.generate(request, context)
        plan.requires_approval = True
        self.store.save(request, context, plan)
        return plan

    def list_plans(self) -> list[dict]:
        return self.store.list()

    def approve(self, plan_id: str, approval: ApprovalRequest) -> dict | None:
        """Records approval only. Execution is intentionally a separate, unimplemented boundary."""
        return self.store.approve(plan_id, approval)
