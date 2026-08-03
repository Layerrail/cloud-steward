import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from cloud_steward.models import ContextSnapshot, ResourceContext
from cloud_steward.settings import Settings


class DataHubContextProvider:
    """Collects governed infrastructure context through DataHub's MCP server."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def collect(self, query: str) -> ContextSnapshot:
        if not self.settings.datahub_enabled:
            return self._sample(query)

        try:
            async with self._session() as session:
                tools = await session.list_tools()
                tool = self._select_search_tool(tools.tools)
                arguments = self._arguments_for(tool, query)
                result = await session.call_tool(tool.name, arguments)
                excerpt = "\n".join(
                    getattr(item, "text", "")
                    for item in result.content
                    if getattr(item, "text", "")
                )
                return ContextSnapshot(
                    query=query,
                    provider="datahub-mcp",
                    tool=tool.name,
                    resources=self._resources_from_text(excerpt),
                    raw_excerpt=excerpt[:5000],
                )
        except Exception as error:  # The UI must explain degraded context instead of hiding it.
            snapshot = self._sample(query)
            snapshot.provider = "datahub-mcp-degraded"
            snapshot.raw_excerpt = f"MCP connection failed: {type(error).__name__}: {error}"
            return snapshot

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[Any]:
        from mcp import ClientSession, StdioServerParameters

        if self.settings.datahub_mcp_url:
            from mcp.client.streamable_http import streamablehttp_client

            headers = {}
            if self.settings.datahub_gms_token:
                headers["Authorization"] = f"Bearer {self.settings.datahub_gms_token}"
            async with (
                streamablehttp_client(
                    self.settings.datahub_mcp_url,
                    headers=headers,
                ) as (read, write, _),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                yield session
            return

        from mcp.client.stdio import stdio_client

        environment = os.environ.copy()
        environment["DATAHUB_GMS_URL"] = self.settings.datahub_gms_url or ""
        if self.settings.datahub_gms_token:
            environment["DATAHUB_GMS_TOKEN"] = self.settings.datahub_gms_token
        params = StdioServerParameters(
            command="uvx",
            args=["mcp-server-datahub"],
            env=environment,
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            yield session

    def _select_search_tool(self, tools: list[Any]) -> Any:
        if self.settings.datahub_search_tool:
            for tool in tools:
                if tool.name == self.settings.datahub_search_tool:
                    return tool
        preferred = ("search", "find", "entity")
        for fragment in preferred:
            for tool in tools:
                if fragment in tool.name.lower() and "document" not in tool.name.lower():
                    return tool
        if not tools:
            raise RuntimeError("DataHub MCP server exposed no tools")
        return tools[0]

    @staticmethod
    def _arguments_for(tool: Any, query: str) -> dict[str, Any]:
        schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", {}) or {}
        properties = schema.get("properties", {})
        for key in ("query", "search_query", "searchQuery", "text", "input"):
            if key in properties:
                return {key: query}
        required = schema.get("required", [])
        if required:
            return {required[0]: query}
        return {"query": query}

    @staticmethod
    def _resources_from_text(text: str) -> list[ResourceContext]:
        if not text.strip():
            return []
        try:
            payload = json.loads(text)
            values = payload if isinstance(payload, list) else payload.get("entities", [])
            resources = []
            for index, value in enumerate(values[:12]):
                if not isinstance(value, dict):
                    continue
                resources.append(
                    ResourceContext(
                        urn=str(value.get("urn", f"urn:context:{index}")),
                        name=str(value.get("name", value.get("title", f"Resource {index + 1}"))),
                        kind=str(value.get("type", "dataset")).lower(),
                        owner=value.get("owner"),
                        tags=[str(tag) for tag in value.get("tags", [])],
                    )
                )
            if resources:
                return resources
        except (json.JSONDecodeError, AttributeError):
            pass
        return [
            ResourceContext(
                urn="urn:li:dataset:datahub-context",
                name="DataHub MCP search result",
                kind="metadata-context",
                evidence=[text[:1200]],
            )
        ]

    @staticmethod
    def _sample(query: str) -> ContextSnapshot:
        resources = [
            ResourceContext(
                urn="urn:li:dataset:(urn:li:dataPlatform:layerrail,checkout-events,PROD)",
                name="checkout-events",
                kind="dataset",
                owner="platform-team",
                environment="PROD",
                tags=["critical", "customer-facing", "pii-reviewed"],
                upstream=["billing-api"],
                downstream=["invoice-worker", "revenue-dashboard"],
                evidence=["Schema contract v4", "Freshness assertion: 15 minutes"],
            ),
            ResourceContext(
                urn="urn:li:dataJob:(urn:li:dataFlow:layerrail,invoice-worker,PROD)",
                name="invoice-worker",
                kind="data-job",
                owner="finance-platform",
                environment="PROD",
                tags=["critical", "approval-required"],
                upstream=["checkout-events"],
                downstream=["invoice-pdfs"],
                evidence=["Last successful deployment: revision 8f12c0a"],
            ),
        ]
        return ContextSnapshot(
            query=query,
            provider="sample-datahub-context",
            tool="search",
            resources=resources,
            raw_excerpt=(
                "Demo context is active. Configure DATAHUB_MCP_URL or DATAHUB_GMS_URL "
                "for live metadata."
            ),
        )
