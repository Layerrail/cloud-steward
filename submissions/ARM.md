# Arm submission checklist

- Devpost submission ID: `1123362`.
- Draft state: 4/5 steps complete; not finally submitted.
- Intended track: Track 2 — Cloud AI.
- Deadline: 2026-08-14 16:00 PT.
- New work: Cloud Steward started 2026-08-02.
- Repository license: Apache-2.0.
- Verified Arm evidence: CI run `30781828308` built the container on a native GitHub-hosted `aarch64` runner and produced a 1,000-iteration deterministic-planning benchmark (0.0105 ms median, 0.0108 ms p95).
- Saved survey answers accurately identify Arm hardware access, track guidance, and benchmarking as the main challenges.
- Local planner implemented: optional CPU-only `llama-completion` inference uses a strict JSON schema, deterministic sampling, bounded governed context, and the existing approval guardrails.
- Native benchmark implemented: the dedicated workflow pins Qwen2.5-0.5B-Instruct and `llama.cpp`, compares FP16, Q4_0, and Q4_0 plus Arm KleidiAI, verifies runtime kernel activation, and checks safety-quality parity.
- Remaining evidence gate: run the new workflow successfully, publish its measured throughput/RSS/model-size results and checksummed artifact, and update the Devpost write-up without presenting the old deterministic benchmark as AI evidence.
- The final Official Rules agreement remains unchecked.
