# CockroachDB × AWS submission checklist

- Devpost submission ID: `1123364`.
- Draft state: 3/5 steps complete; not finally submitted.
- Deadline: 2026-08-18 17:00 ET.
- New work: Cloud Steward started 2026-08-02.
- Verified CockroachDB evidence: CI run `30781828308` starts a secure CockroachDB v26.2 node, creates and recalls a durable plan, and verifies the `steward_memory_embedding_idx` distributed vector index.
- Currently verified listed CockroachDB tool: Distributed Vector Indexing.
- Remaining CockroachDB gate: meaningfully integrate at least one additional listed tool — Cloud Managed MCP Server, `ccloud` CLI, or Agent Skills Repo.
- Remaining AWS gate: deploy the working agent on at least one qualifying AWS service. The ECS ARM64 task definition is a template, not deployment evidence.
- Remaining video gate: record the CockroachDB memory layer operating in the AWS-hosted application.
- Do not select two tools or any AWS service in Devpost until the corresponding runtime evidence exists.
- The final Official Rules agreement remains unchecked.
