# Arm submission checklist

- Devpost submission ID: `1123362`.
- Draft state: 4/5 steps complete; not finally submitted.
- Intended track: Track 2 — Cloud AI.
- Deadline: 2026-08-14 16:00 PT.
- New work: Cloud Steward started 2026-08-02.
- Repository license: Apache-2.0.
- Verified Arm evidence: CI run `30781828308` built the container on a native GitHub-hosted `aarch64` runner and produced a 1,000-iteration deterministic-planning benchmark (0.0105 ms median, 0.0108 ms p95).
- Saved survey answers accurately identify Arm hardware access, track guidance, and benchmarking as the main challenges.
- Remaining technical gate: run a genuine AI inference workload on Arm-powered compute and publish meaningful before/after optimization, memory, latency, or throughput evidence. The current Gemini call is remote and the deterministic benchmark alone is not sufficient Track 2 evidence.
- Remaining write-up gate: clearly identify Cloud AI, Arm-powered runtime, setup instructions, optimization output, and reusable benchmark artifacts.
- The final Official Rules agreement remains unchecked.
