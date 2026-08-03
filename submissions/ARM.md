# Arm submission checklist

- Devpost submission ID: `1123362`.
- Status: Submitted 2026-08-03T12:42:53.089-04:00, confirmed via `get_project` (`hackathons[].submitted_at`).
- Intended track: Track 2 — Cloud AI.
- Track fit: native CPU-only inference on a cloud-hosted Arm64 runner, Q4_0 quantization, `llama.cpp`, verified KleidiAI activation, and an agentic planning workload.
- Deadline: 2026-08-14 16:00 PT.
- New work: Cloud Steward started 2026-08-02.
- Repository license: Apache-2.0.
- Verified Arm evidence: CI run `30781828308` built the container on a native GitHub-hosted `aarch64` runner and produced a 1,000-iteration deterministic-planning benchmark (0.0105 ms median, 0.0108 ms p95).
- Saved survey answers accurately identify Arm hardware access, track guidance, and benchmarking as the main challenges.
- Local planner implemented: optional CPU-only `llama-completion` inference uses a strict JSON schema, deterministic sampling, bounded governed context, and the existing approval guardrails.
- Native benchmark implemented: the dedicated workflow pins Qwen2.5-0.5B-Instruct and `llama.cpp`, compares FP16, Q4_0, and Q4_0 plus Arm KleidiAI, verifies runtime kernel activation, and checks safety-quality parity.
- A demonstration video is optional for this challenge; the public repository, detailed write-up, setup instructions, source, and proof artifacts are required.
- Evidence gate completed 2026-08-03: native run `30822464850` passed on a four-vCPU Arm Neoverse-N2 runner and produced checksummed JSON plus retained raw artifacts.
- Verified FP16 comparison: 66.46% smaller model, 54.39% lower peak RSS, 2.237x prompt throughput, and 1.922x generation throughput for Q4_0 plus KleidiAI.
- Transparent backend comparison: verified KleidiAI measured 0.998x prompt and 0.993x generation throughput versus regular Q4_0, so quantization—not an extra KleidiAI speedup—is the material optimization claimed.
- Publication gate completed 2026-08-03: the public Devpost story includes the measured Cloud AI section, evidence URL, exact results, and no-speedup disclosure.
- The Official Rules agreement was accepted by the project author and the final submission was authorized and executed 2026-08-03.
