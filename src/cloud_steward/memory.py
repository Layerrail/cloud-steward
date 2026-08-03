import json
import math
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, String, Text, create_engine, select, text
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
        self.vector_index_enabled = database_url.startswith("cockroachdb")
        if self.vector_index_enabled:
            self._initialize_vector_memory()

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
        if self.vector_index_enabled:
            self._save_vector(str(plan.id), plan.goal)

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

    def search_similar(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        embedding = self._embedding(query)
        if self.vector_index_enabled:
            vector = self._vector_literal(embedding)
            statement = text(
                """
                SELECT plan_id, goal,
                       embedding <=> CAST(:embedding AS VECTOR) AS distance
                FROM steward_memory_vector
                ORDER BY embedding <=> CAST(:embedding AS VECTOR)
                LIMIT :limit
                """
            )
            with self.engine.connect() as connection:
                rows = connection.execute(
                    statement,
                    {"embedding": vector, "limit": limit},
                ).mappings()
                return [
                    {
                        "plan_id": str(row["plan_id"]),
                        "goal": row["goal"],
                        "similarity": round(1 - float(row["distance"]), 6),
                        "provider": "cockroachdb-vector-index",
                    }
                    for row in rows
                ]

        records = self.list(limit=100)
        scored = []
        for record in records:
            similarity = self._cosine(embedding, self._embedding(record["goal"]))
            scored.append(
                {
                    "plan_id": record["id"],
                    "goal": record["goal"],
                    "similarity": round(similarity, 6),
                    "provider": "local-deterministic-fallback",
                }
            )
        return sorted(scored, key=lambda item: item["similarity"], reverse=True)[:limit]

    def _initialize_vector_memory(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS steward_memory_vector (
                        plan_id UUID PRIMARY KEY,
                        goal STRING NOT NULL,
                        embedding VECTOR(8) NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE VECTOR INDEX IF NOT EXISTS steward_memory_embedding_idx
                    ON steward_memory_vector (embedding vector_cosine_ops)
                    """
                )
            )

    def _save_vector(self, plan_id: str, goal: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPSERT INTO steward_memory_vector (plan_id, goal, embedding)
                    VALUES (CAST(:plan_id AS UUID), :goal, CAST(:embedding AS VECTOR))
                    """
                ),
                {
                    "plan_id": plan_id,
                    "goal": goal,
                    "embedding": self._vector_literal(self._embedding(goal)),
                },
            )

    @staticmethod
    def _embedding(value: str) -> list[float]:
        """Stable eight-dimensional demo embedding with no external data transfer."""
        digest = sha256(value.lower().encode("utf-8")).digest()
        vector = [((digest[index] / 255) * 2) - 1 for index in range(8)]
        magnitude = math.sqrt(sum(component * component for component in vector)) or 1
        return [component / magnitude for component in vector]

    @staticmethod
    def _vector_literal(vector: list[float]) -> str:
        return "[" + ",".join(f"{component:.8f}" for component in vector) + "]"

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        return sum(a * b for a, b in zip(left, right, strict=True))

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
