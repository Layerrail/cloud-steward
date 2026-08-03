import platform

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from cloud_steward import __version__
from cloud_steward.datahub import DataHubContextProvider
from cloud_steward.memory import PlanStore
from cloud_steward.models import (
    ActionPlan,
    ApprovalRequest,
    IntegrationStatus,
    PlanRequest,
    StatusResponse,
)
from cloud_steward.planner import PlanGenerator
from cloud_steward.service import StewardService
from cloud_steward.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    store = PlanStore(settings.database_url)
    service = StewardService(
        context_provider=DataHubContextProvider(settings),
        planner=PlanGenerator(settings),
        store=store,
    )

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Governed context, reversible plans, named human approval.",
    )
    app.state.settings = settings
    app.state.service = service

    assets_dir = settings.static_dir / "assets"
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(settings.static_dir / "index.html")

    @app.get("/api/status", response_model=StatusResponse)
    async def service_status() -> StatusResponse:
        return StatusResponse(
            service=settings.app_name,
            version=__version__,
            architecture=platform.machine().lower(),
            safeguards=[
                "Dry-run by default",
                "Named human approval",
                "No execution boundary",
                "Untrusted metadata isolation",
                "Durable audit memory",
            ],
            integrations=[
                IntegrationStatus(
                    name="DataHub MCP",
                    configured=settings.datahub_enabled,
                    mode="live" if settings.datahub_enabled else "sample",
                    detail="Governed metadata, lineage, ownership, and impact context",
                ),
                IntegrationStatus(
                    name="Gemini",
                    configured=settings.gemini_enabled,
                    mode="live" if settings.gemini_enabled else "deterministic",
                    detail=f"Structured action planning with {settings.gemini_model}",
                ),
                IntegrationStatus(
                    name="CockroachDB memory",
                    configured=settings.database_url.startswith(("cockroachdb", "postgres")),
                    mode=(
                        "distributed"
                        if settings.database_url.startswith(("cockroachdb", "postgres"))
                        else "local"
                    ),
                    detail="Plan, context, approval, and incident audit trail",
                ),
            ],
        )

    @app.post("/api/plans", response_model=ActionPlan, status_code=status.HTTP_201_CREATED)
    async def propose_plan(request: PlanRequest) -> ActionPlan:
        return await service.propose(request)

    @app.get("/api/plans")
    async def list_plans() -> list[dict]:
        return service.list_plans()

    @app.post("/api/plans/{plan_id}/approve")
    async def approve_plan(plan_id: str, approval: ApprovalRequest) -> dict:
        record = service.approve(plan_id, approval)
        if not record:
            raise HTTPException(status_code=404, detail="Plan not found")
        return record

    @app.get("/healthz", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()


def run() -> None:
    uvicorn.run(
        "cloud_steward.main:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
    )


if __name__ == "__main__":
    run()
