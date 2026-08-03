"""Capture a redacted, reproducible read-only DataHub MCP context snapshot."""

import argparse
import asyncio
import json
from hashlib import sha256
from pathlib import Path

from cloud_steward.datahub import DataHubContextProvider
from cloud_steward.settings import Settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--query",
        default="revenue orders customer",
        help="Catalog query used for the evidence snapshot.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/evidence/datahub-context.json"),
        help="JSON evidence output path.",
    )
    return parser.parse_args()


async def capture(query: str, output: Path) -> None:
    snapshot = await DataHubContextProvider(Settings()).collect(query)
    if snapshot.provider != "datahub-mcp":
        raise RuntimeError(
            f"Expected live DataHub MCP context, received {snapshot.provider}: "
            f"{snapshot.raw_excerpt[:300]}"
        )
    if not snapshot.resources:
        raise RuntimeError("DataHub MCP returned no governed resources")
    required_tools = {"search", "get_entities", "get_lineage"}
    used_tools = {tool.strip() for tool in snapshot.tool.split(",")}
    if missing_tools := required_tools - used_tools:
        raise RuntimeError(
            f"DataHub MCP evidence is missing read-only tools: {sorted(missing_tools)}"
        )
    has_governance = any(
        resource.owner or resource.tags or resource.evidence
        for resource in snapshot.resources
    )
    has_lineage = any(
        resource.upstream or resource.downstream
        for resource in snapshot.resources
    )
    if not has_governance:
        raise RuntimeError(
            "DataHub MCP returned no ownership, tags, domain, or description evidence"
        )
    if not has_lineage:
        raise RuntimeError("DataHub MCP returned no upstream or downstream lineage")

    serialized = snapshot.model_dump(mode="json")
    serialized_text = json.dumps(serialized)
    forbidden = ("authorization: bearer", "datahub_gms_token", "access_token")
    if any(marker in serialized_text.lower() for marker in forbidden):
        raise RuntimeError("Refusing to write evidence that may contain a credential")

    output.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(serialized, indent=2) + "\n").encode()
    output.write_bytes(content)
    digest = sha256(content).hexdigest()
    output.with_suffix(f"{output.suffix}.sha256").write_text(
        f"{digest}  {output.name}\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "provider": snapshot.provider,
                "tools": snapshot.tool,
                "resources": len(snapshot.resources),
                "governance": has_governance,
                "lineage": has_lineage,
                "output": str(output),
                "sha256": digest,
            }
        )
    )


def main() -> None:
    args = parse_args()
    asyncio.run(capture(args.query, args.output))


if __name__ == "__main__":
    main()
