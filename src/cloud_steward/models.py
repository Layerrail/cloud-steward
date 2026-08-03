from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class RiskLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class PlanStatus(StrEnum):
    proposed = "proposed"
    approved = "approved"
    rejected = "rejected"


class ResourceContext(BaseModel):
    urn: str
    name: str
    kind: str = "dataset"
    owner: str | None = None
    environment: str | None = None
    tags: list[str] = Field(default_factory=list)
    upstream: list[str] = Field(default_factory=list)
    downstream: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class ContextSnapshot(BaseModel):
    query: str
    provider: str
    tool: str
    resources: list[ResourceContext]
    raw_excerpt: str = ""
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProposedAction(BaseModel):
    order: int = Field(ge=1)
    action: str
    target: str
    reason: str
    expected_result: str
    verification: str
    rollback: str
    risk: RiskLevel
    mutation: bool = False


class ActionPlan(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    goal: str
    summary: str
    assumptions: list[str] = Field(default_factory=list)
    context_findings: list[str] = Field(default_factory=list)
    actions: list[ProposedAction]
    overall_risk: RiskLevel
    status: PlanStatus = PlanStatus.proposed
    requires_approval: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PlanRequest(BaseModel):
    goal: str = Field(min_length=8, max_length=1000)
    context_query: str = Field(min_length=2, max_length=300)
    environment: str = Field(default="production", max_length=40)
    dry_run: bool = True


class ApprovalRequest(BaseModel):
    approved_by: str = Field(min_length=2, max_length=120)
    note: str = Field(default="", max_length=500)


class IntegrationStatus(BaseModel):
    name: str
    configured: bool
    mode: str
    detail: str


class StatusResponse(BaseModel):
    service: str
    version: str
    architecture: str
    safeguards: list[str]
    integrations: list[IntegrationStatus]
