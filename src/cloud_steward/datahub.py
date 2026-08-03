import json
import os
import re
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from cloud_steward.models import ContextSnapshot, ResourceContext
from cloud_steward.settings import Settings


class DataHubContextProvider:
    """Collects governed infrastructure context through DataHub's MCP server."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.runtime_mode = "configured" if settings.datahub_enabled else "sample"

    async def collect(self, query: str) -> ContextSnapshot:
        if not self.settings.datahub_enabled:
            return self._sample(query)

        try:
            async with self._session() as session:
                listed_tools = await session.list_tools()
                tools = listed_tools.tools
                search_tool = self._select_search_tool(tools)
                arguments = self._arguments_for(search_tool, query)
                result = await session.call_tool(search_tool.name, arguments)
                search_payload = self._result_payload(result)
                resources = self._resources_from_payload(search_payload)
                evidence: dict[str, Any] = {"search": search_payload}
                used_tools = [search_tool.name]

                entity_tool = self._tool_named(tools, "get_entities")
                if entity_tool and resources:
                    entity_result = await session.call_tool(
                        entity_tool.name,
                        {"urns": [resources[0].urn]},
                    )
                    entity_payload = self._result_payload(entity_result)
                    resources = self._merge_resources(
                        resources,
                        self._resources_from_payload(entity_payload),
                    )
                    evidence["entities"] = entity_payload
                    used_tools.append(entity_tool.name)

                lineage_tool = self._tool_named(tools, "get_lineage")
                datasets = [
                    resource for resource in resources if resource.kind == "dataset"
                ][:4]
                if lineage_tool and datasets:
                    lineage_evidence = {}
                    for dataset in datasets:
                        dataset_evidence = {}
                        for upstream, direction in (
                            (True, "upstream"),
                            (False, "downstream"),
                        ):
                            lineage_result = await session.call_tool(
                                lineage_tool.name,
                                {
                                    "urn": dataset.urn,
                                    "upstream": upstream,
                                    "max_hops": 1,
                                    "max_results": 8,
                                },
                            )
                            lineage_payload = self._result_payload(lineage_result)
                            self._apply_lineage(
                                resources,
                                dataset.urn,
                                lineage_payload,
                                upstream,
                            )
                            dataset_evidence[direction] = lineage_payload
                        lineage_evidence[dataset.urn] = dataset_evidence
                        if dataset.upstream or dataset.downstream:
                            break
                    evidence["lineage"] = lineage_evidence
                    used_tools.append(lineage_tool.name)

                self.runtime_mode = "live"
                excerpt = {
                    "mcp_tools": used_tools,
                    "search_total": self._search_total(search_payload),
                    "resources": [
                        resource.model_dump(mode="json") for resource in resources[:8]
                    ],
                }
                return ContextSnapshot(
                    query=query,
                    provider="datahub-mcp",
                    tool=", ".join(used_tools),
                    resources=resources,
                    raw_excerpt=json.dumps(excerpt, default=str)[:5000],
                )
        except Exception as error:  # The UI must explain degraded context instead of hiding it.
            self.runtime_mode = "degraded"
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
        environment["TOOLS_IS_MUTATION_ENABLED"] = "false"
        environment["TOOLS_IS_USER_ENABLED"] = "false"
        environment["DATAHUB_MCP_DOCUMENT_TOOLS_DISABLED"] = "true"
        if self.settings.datahub_gms_token:
            environment["DATAHUB_GMS_TOKEN"] = self.settings.datahub_gms_token
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_server_datahub"],
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

    @classmethod
    def _arguments_for(cls, tool: Any, query: str) -> dict[str, Any]:
        schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", {}) or {}
        properties = schema.get("properties", {})
        arguments: dict[str, Any] = {}
        for key in ("query", "search_query", "searchQuery", "text", "input"):
            if key in properties:
                arguments[key] = cls._normalize_search_query(tool, query)
                break
        if "num_results" in properties:
            arguments["num_results"] = 8
        if arguments:
            return arguments
        required = schema.get("required", [])
        if required:
            return {required[0]: query}
        return {"query": query}

    @staticmethod
    def _normalize_search_query(tool: Any, query: str) -> str:
        if tool.name != "search" or query.lstrip().startswith("/q"):
            return query
        terms = re.findall(r"[A-Za-z0-9_.-]+", query)
        return "/q " + " OR ".join(terms) if terms else "*"

    @staticmethod
    def _tool_named(tools: list[Any], name: str) -> Any | None:
        return next((tool for tool in tools if tool.name == name), None)

    @classmethod
    def _result_payload(cls, result: Any) -> Any:
        structured = getattr(result, "structuredContent", None) or getattr(
            result, "structured_content", None
        )
        if structured is not None:
            return cls._unwrap_result(structured)
        text_content = "\n".join(
            getattr(item, "text", "")
            for item in getattr(result, "content", [])
            if getattr(item, "text", "")
        )
        if not text_content.strip():
            return {}
        try:
            return cls._unwrap_result(json.loads(text_content))
        except json.JSONDecodeError:
            return {"text": text_content}

    @staticmethod
    def _unwrap_result(payload: Any) -> Any:
        while isinstance(payload, dict) and set(payload) == {"result"}:
            payload = payload["result"]
        return payload

    @staticmethod
    def _search_total(payload: Any) -> int | None:
        if not isinstance(payload, dict):
            return None
        total = payload.get("total")
        return total if isinstance(total, int) else None

    @classmethod
    def _resources_from_payload(cls, payload: Any) -> list[ResourceContext]:
        if not payload:
            return []
        if isinstance(payload, list):
            values = payload
        elif isinstance(payload, dict) and isinstance(payload.get("searchResults"), list):
            values = [item.get("entity", item) for item in payload["searchResults"]]
        elif isinstance(payload, dict) and isinstance(payload.get("entities"), list):
            values = payload["entities"]
        elif isinstance(payload, dict) and payload.get("urn"):
            values = [payload]
        else:
            values = []

        resources = []
        for value in values[:12]:
            if not isinstance(value, dict):
                continue
            resource = cls._resource_from_entity(value)
            if resource:
                resources.append(resource)
        if resources:
            return resources

        text = payload.get("text", "") if isinstance(payload, dict) else str(payload)
        if not text.strip():
            return []
        return [
            ResourceContext(
                urn="urn:li:dataset:datahub-context",
                name="DataHub MCP search result",
                kind="metadata-context",
                evidence=[text[:1200]],
            )
        ]

    @classmethod
    def _resource_from_entity(cls, entity: dict[str, Any]) -> ResourceContext | None:
        urn = str(entity.get("urn", "")).strip()
        if not urn:
            return None
        properties = entity.get("properties") or {}
        editable = entity.get("editableProperties") or {}
        name = str(
            properties.get("name")
            or editable.get("name")
            or entity.get("name")
            or urn
        )
        entity_type = str(entity.get("type") or entity.get("__typename") or "")
        kind = cls._kind_from(entity_type, urn)

        owners = (entity.get("ownership") or {}).get("owners") or []
        owner = None
        for assignment in owners:
            principal = assignment.get("owner") or {}
            principal_properties = principal.get("properties") or {}
            principal_editable = principal.get("editableProperties") or {}
            owner = (
                principal_properties.get("displayName")
                or principal_editable.get("displayName")
                or principal_properties.get("email")
                or principal.get("name")
                or principal.get("urn")
            )
            if owner:
                owner = str(owner)
                break

        tags = []
        for assignment in (entity.get("tags") or entity.get("globalTags") or {}).get(
            "tags", []
        ):
            tag = assignment.get("tag") or assignment
            tag_name = (tag.get("properties") or {}).get("name") or tag.get("name") or tag.get(
                "urn"
            )
            if tag_name:
                tags.append(str(tag_name))

        evidence = []
        description = properties.get("description") or editable.get("description")
        if description:
            evidence.append(str(description)[:500])
        platform = entity.get("platform") or {}
        platform_name = (
            (platform.get("properties") or {}).get("displayName")
            or platform.get("name")
        )
        if platform_name:
            evidence.append(f"Platform: {platform_name}")
        domain = (entity.get("domain") or {}).get("domain") or {}
        domain_name = (domain.get("properties") or {}).get("name")
        if domain_name:
            evidence.append(f"Domain: {domain_name}")

        glossary_terms = []
        for assignment in (entity.get("glossaryTerms") or {}).get("terms", []):
            term = assignment.get("term") or assignment
            term_name = (term.get("properties") or {}).get("name") or term.get("name")
            if term_name:
                glossary_terms.append(str(term_name))
        if glossary_terms:
            evidence.append(
                f"Glossary terms: {', '.join(dict.fromkeys(glossary_terms))}"
            )

        for assignment in (entity.get("structuredProperties") or {}).get(
            "properties", []
        ):
            structured_property = assignment.get("structuredProperty") or {}
            definition = structured_property.get("definition") or {}
            property_name = (
                definition.get("displayName")
                or definition.get("qualifiedName")
                or structured_property.get("urn")
            )
            values = []
            for value in assignment.get("values") or []:
                selected = next(
                    (
                        value.get(key)
                        for key in ("stringValue", "numberValue", "booleanValue")
                        if value.get(key) is not None
                    ),
                    None,
                )
                if selected is not None:
                    values.append(str(selected))
            if property_name and values:
                evidence.append(f"{property_name}: {', '.join(values)}")
            if owner is None and property_name == "Data Owner Escalation Contact":
                value_entities = assignment.get("valueEntities") or []
                if value_entities:
                    value_entity = value_entities[0]
                    value_properties = value_entity.get("properties") or {}
                    owner = str(
                        value_properties.get("displayName")
                        or value_properties.get("email")
                        or value_entity.get("urn")
                    )

        for health in entity.get("health") or []:
            health_type = health.get("type")
            health_status = health.get("status")
            if health_type and health_status:
                evidence.append(f"{health_type}: {health_status}")

        return ResourceContext(
            urn=urn,
            name=name,
            kind=kind,
            owner=owner,
            environment=cls._environment_from_urn(urn),
            tags=tags,
            evidence=evidence,
        )

    @staticmethod
    def _kind_from(entity_type: str, urn: str) -> str:
        value = entity_type.removesuffix("Entity").replace("_", "-").lower()
        if value:
            return value
        urn_type = urn.removeprefix("urn:li:").split(":", 1)[0]
        aliases = {"dataJob": "data-job", "dataFlow": "data-flow"}
        return aliases.get(urn_type, urn_type.replace("_", "-").lower())

    @staticmethod
    def _environment_from_urn(urn: str) -> str | None:
        if urn.startswith("urn:li:dataset:(") and urn.endswith(")"):
            environment = urn.rsplit(",", 1)[-1].removesuffix(")").strip()
            return environment or None
        return None

    @staticmethod
    def _merge_resources(
        initial: list[ResourceContext], detailed: list[ResourceContext]
    ) -> list[ResourceContext]:
        by_urn = {resource.urn: resource for resource in initial}
        for detail in detailed:
            current = by_urn.get(detail.urn)
            if not current:
                initial.append(detail)
                by_urn[detail.urn] = detail
                continue
            current.name = detail.name or current.name
            current.kind = detail.kind or current.kind
            current.owner = detail.owner or current.owner
            current.environment = detail.environment or current.environment
            current.tags = list(dict.fromkeys([*current.tags, *detail.tags]))
            current.evidence = list(dict.fromkeys([*current.evidence, *detail.evidence]))
        return initial

    @classmethod
    def _apply_lineage(
        cls,
        resources: list[ResourceContext],
        urn: str,
        payload: Any,
        upstream: bool,
    ) -> None:
        if not isinstance(payload, dict):
            return
        direction = "upstreams" if upstream else "downstreams"
        results = (payload.get(direction) or {}).get("searchResults") or []
        names = []
        for item in results:
            entity = item.get("entity", item) if isinstance(item, dict) else {}
            resource = cls._resource_from_entity(entity)
            if resource:
                names.append(resource.name)
        target = next((resource for resource in resources if resource.urn == urn), None)
        if not target:
            return
        if upstream:
            target.upstream = list(dict.fromkeys(names))
        else:
            target.downstream = list(dict.fromkeys(names))

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
