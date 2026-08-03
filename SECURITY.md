# Security policy

Cloud Steward is an approval-first prototype. It intentionally has no infrastructure execution endpoint.

## Guardrails

- Metadata and model output are treated as untrusted input.
- API keys and tokens are accepted only through environment variables.
- The public status endpoint reports configuration state, never secret values.
- Every plan defaults to dry-run and requires named human approval.
- Approval records intent but cannot execute a plan.
- Mutating DataHub MCP tools are not selected by the application.

Report vulnerabilities privately to security@layerrail.com. Do not include credentials or customer data.
