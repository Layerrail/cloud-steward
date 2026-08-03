# CALL-E submission checklist

- Devpost submission ID: `1123365`.
- Draft state: 3/5 steps complete; not finally submitted.
- Conservative deadline: 2026-09-14 04:45 WAT because the rules text says 11:45 SGT while the portal displays a later EDT-derived time.
- Contribution PR: https://github.com/CALLE-AI/awesome-phone-call-agents/pull/70
- Contribution path: `apps/python/cloud-steward-incident-callback`.
- Verified evidence: preview-first consent checks, E.164 validation, masked output, idempotency, official CLI plan/run/status flow, four passing app tests, and passing upstream validation.
- Safety boundary: a phone response may acknowledge or request review, but it never approves or executes infrastructure.
- Remaining account gate: CALL-E OAuth reached Google account selection, but the account chooser requires a human security click. No associated CALL-E account email is available yet.
- Remaining runtime gate: authenticate CALL-E and prove that CALL-E is actually called at runtime. No live call has been made.
- A live call may target only a recipient who explicitly consented to this operational incident call; do not infer consent or use a third party.
- Remaining demo gate: record a public video under three minutes showing the functional CALL-E path.
- Required eligibility attestations and final Official Rules agreement remain unchecked.
