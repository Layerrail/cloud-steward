import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from cloud_steward.models import (
    ActionPlan,
    ApprovalRequest,
    ContextSnapshot,
    PlanRequest,
    PlanStatus,
)


class Base(DeclarativeBase):
    pass


class PlanRecord(Base):
    __tablename__ = "steward_plan"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    goal: Mapped[str] = mapped_column(Text)
    request_json: Mapped[str] = mapped_column(Text)
    context_json: Mapped[str] = mapped_column(Text)
    plan_json: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlanStore:
    """Durable audit memory compatible with SQLite and CockroachDB/PostgreSQL."""

    def __init__(self, database_url: str):
        if database_url.startswith("sqlite:///"):
            db_path = Path(database_url.removeprefix("sqlite:///"))
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(database_url, pool_pre_ping=True)
        Base.metadata.create_all(self.engine)

    def save(self, request: PlanRequest, context: ContextSnapshot, plan: ActionPlan) -> None:
        now = datetime.now(UTC)
        record = PlanRecord(
            id=str(plan.id),
            status=plan.status.value,
            goal=plan.goal,
            request_json=request.model_dump_json(),
            context_json=context.model_dump_json(),
            plan_json=plan.model_dump_json(),
            created_at=now,
            updated_at=now,
        )
        with Session(self.engine) as session:
            session.add(record)
            session.commit()

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            records = session.scalars(
                select(PlanRecord).order_by(PlanRecord.created_at.desc()).limit(limit)
            ).all()
            return [self._serialize(record) for record in records]

    def get(self, plan_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            record = session.get(PlanRecord, plan_id)
            return self._serialize(record) if record else None

    def approve(self, plan_id: str, approval: ApprovalRequest) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            record = session.get(PlanRecord, plan_id)
            if not record:
                return None
            payload = json.loads(record.plan_json)
            payload["status"] = PlanStatus.approved.value
            record.plan_json = json.dumps(payload)
            record.status = PlanStatus.approved.value
            record.approved_by = approval.approved_by
            record.approval_note = approval.note
            record.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return self._serialize(record)

    @staticmethod
    def _serialize(record: PlanRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "status": record.status,
            "goal": record.goal,
            "request": json.loads(record.request_json),
            "context": json.loads(record.context_json),
            "plan": json.loads(record.plan_json),
            "approved_by": record.approved_by,
            "approval_note": record.approval_note,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }
