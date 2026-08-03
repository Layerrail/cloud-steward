# Native Arm64 local inference

Cloud Steward can run its structured planning step locally through `llama.cpp` instead of sending governed context to a remote model. This path is designed for CPU-only Arm64 cloud hosts and retains the same dry-run, risk escalation, verification, rollback, and named-approval guardrails as the Gemini and deterministic planners.

## Reproducible optimization comparison

The dedicated `Native Arm inference` workflow runs on GitHub's native `ubuntu-24.04-arm` runner. For public repositories, GitHub documents this runner class as a fresh Arm64 virtual machine with 4 vCPUs, 16 GB RAM, and 14 GB SSD. The exact CPU model is recorded for every run because GitHub does not promise one specific Arm processor.

The workflow pins and checksum-verifies:

- `llama.cpp` commit `1464c62d88f699ec9700c8010bbfdbc603a9efd6`;
- official `Qwen/Qwen2.5-0.5B-Instruct-GGUF` revision `9217f5db79a29953eb74d5343926648285ec7e67`;
- FP16 SHA-256 `8e0ae26000627ed62de0e78e41860af70094558b9d2913385c842a6aa06cf3fc`; and
- Q4_0 SHA-256 `7671c0c304e6ce5a7fc577bcb12aba01e2c155cc2efd29b2213c95b18edaf6ed`.

It builds two CPU-only `llama.cpp` binaries from the same commit and toolchain:

1. the regular optimized CPU backend with KleidiAI disabled; and
2. the same backend with `GGML_CPU_KLEIDIAI=ON`.

Three configurations are measured with 4 threads, five repetitions, a 512-token prompt-processing test, a 128-token generation test, no GPU layers, no accelerator device, and non-mapped model loading for comparable peak RSS:

- FP16 on the regular CPU backend;
- Q4_0 on the regular CPU backend; and
- Q4_0 on the Arm KleidiAI backend.

The workflow refuses to label a result as KleidiAI unless runtime logs contain both the selected primary Q4 kernel feature and a `CPU_KLEIDIAI` model buffer. It also runs the real Cloud Steward planner with FP16 and optimized Q4_0. Both outputs must pass identical structural safety gates; this checks guardrail parity, not identical prose or mathematical equivalence between precisions.

Run it from the Actions tab or on a native Arm64 Ubuntu host after installing Python 3.12+, CMake, Ninja, a C/C++ toolchain, curl, Git, and GNU time:

```shell
pip install -e .
bash deploy/run_arm_inference_benchmark.sh
```

Generated models, source builds, and raw artifacts remain gitignored. The CI artifact contains raw JSONL, activation logs, peak-RSS records, safety-gated sample plans, a normalized JSON summary, and a checksum. Only credential-scanned summaries are committed under `docs/evidence`.

## Use local planning

Build a CPU-only `llama-completion`, download a compatible instruction model, then set:

```text
LLAMA_CPP_BINARY=/opt/llama.cpp/build/bin/llama-completion
LLAMA_CPP_MODEL_PATH=/opt/models/qwen2.5-0.5b-instruct-q4_0.gguf
LLAMA_CPP_MODEL_NAME=Qwen2.5-0.5B-Instruct Q4_0 + KleidiAI
LLAMA_CPP_THREADS=4
```

When both paths are configured, local inference takes precedence over Gemini. The model receives a bounded, normalized governed-context excerpt rather than raw MCP output. `llama-completion` is invoked without a shell, with conversation mode disabled, a strict JSON schema, deterministic sampling, CPU-only flags, a timeout, and captured output. This avoids feeding chat-template role markers into the JSON grammar. Cloud Steward then validates the result and reapplies its non-negotiable guardrails.

This repository does not distribute the Qwen model or `llama.cpp` binaries. Qwen2.5-0.5B-Instruct-GGUF is Apache-2.0; `llama.cpp` is MIT; KleidiAI carries its upstream license notices.