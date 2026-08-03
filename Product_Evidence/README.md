# Cloud Steward product evidence

Cloud Steward began on 2026-08-02. This folder separates verified evidence from requirements that are not yet satisfied.

## Verified on 2026-08-03

- Public source: https://github.com/Layerrail/cloud-steward
- Public demo: https://cloud-steward.onrender.com
- Public live-DataHub walkthrough: https://youtu.be/xW0RnBrROeA
- Original public sample-mode walkthrough: https://youtu.be/tI2ZgGVbZcA
- Public CI: https://github.com/Layerrail/cloud-steward/actions/runs/30781828308
- The CI run passed Python 3.12 and 3.13 tests, a native `aarch64` container build and benchmark, a secure CockroachDB vector-memory integration, and one live Gemini schema-constrained planning call.
- Native Arm inference run https://github.com/Layerrail/cloud-steward/actions/runs/30822464850 passed on a four-vCPU Neoverse-N2 runner. Checksummed evidence records Qwen2.5-0.5B-Instruct FP16, Q4_0, and verified KleidiAI measurements plus structural safety parity.
- A separate local run captured governed DataHub Core ownership, glossary, structured properties, health, and one-hop lineage through the read-only open-source MCP server. The public demo remains in sample mode.
- The public demo's `/api/status` response truthfully reports sample DataHub context, deterministic planning, and local memory.

## Current business evidence

- Cloud Steward users: 0 verified users.
- Arms-length revenue: $0.
- Related-party revenue: $0.
- Marketing and customer-acquisition spend: $0.
- Project-specific expenses: not finalized; do not report an estimate as an audited total.

LayerRail's separate 36-person beta cohort is not Cloud Steward adoption and must not be included here.

## Missing before a valid Gemini XPRIZE submission

- A working deployment using at least one Google Cloud product.
- Gemini API calls in that deployed application, not only isolated CI.
- Monthly Google Cloud invoices or zero-dollar cost statements for the competition period.
- Gemini observability dashboard screenshots and production execution logs.
- Consenting real users, dated feedback, and supportable revenue/expense records.

The available Google Cloud billing accounts are currently closed. This repository does not claim a Google Cloud deployment until that is resolved and evidenced.
