"""Convert raw native Arm llama.cpp measurements into reviewable evidence."""

import argparse
import hashlib
import json
import os
import platform
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LLAMA_CPP_COMMIT = "1464c62d88f699ec9700c8010bbfdbc603a9efd6"
MODEL_REVISION = "9217f5db79a29953eb74d5343926648285ec7e67"
MODEL_HASHES = {
    "fp16": "8e0ae26000627ed62de0e78e41860af70094558b9d2913385c842a6aa06cf3fc",
    "q4_0": "7671c0c304e6ce5a7fc577bcb12aba01e2c155cc2efd29b2213c95b18edaf6ed",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if len(records) != 2:
        raise RuntimeError(f"Expected prompt and generation records in {path}, got {len(records)}")
    return records


def read_rss(path: Path) -> int:
    match = re.search(r"max_rss_kib=(\d+)", path.read_text())
    if not match:
        raise RuntimeError(f"Peak RSS was not captured in {path}")
    return int(match.group(1))


def measurement(raw_dir: Path, label: str) -> dict[str, Any]:
    records = read_jsonl(raw_dir / f"{label}.jsonl")
    prompt = next(record for record in records if record["n_prompt"] > 0)
    generation = next(record for record in records if record["n_gen"] > 0)
    if prompt["build_commit"] != LLAMA_CPP_COMMIT[:7]:
        raise RuntimeError(f"Unexpected llama.cpp build commit: {prompt['build_commit']}")
    return {
        "model_type": prompt["model_type"],
        "model_size_bytes": prompt["model_size"],
        "model_parameters": prompt["model_n_params"],
        "threads": prompt["n_threads"],
        "devices": prompt["devices"],
        "load_mode": prompt["load_mode"],
        "prompt_tokens": prompt["n_prompt"],
        "prompt_tokens_per_second": round(prompt["avg_ts"], 3),
        "prompt_stddev_tokens_per_second": round(prompt["stddev_ts"], 3),
        "generation_tokens": generation["n_gen"],
        "generation_tokens_per_second": round(generation["avg_ts"], 3),
        "generation_stddev_tokens_per_second": round(generation["stddev_ts"], 3),
        "peak_rss_kib": read_rss(raw_dir / f"{label}.rss"),
        "raw_sha256": hashlib.sha256((raw_dir / f"{label}.jsonl").read_bytes()).hexdigest(),
    }


def speedup(new: float, baseline: float) -> float:
    return round(new / baseline, 3)


def reduction(new: float, baseline: float) -> float:
    return round((1 - new / baseline) * 100, 2)


def concise_cpu(lscpu: str) -> dict[str, str]:
    wanted = {"Architecture", "Model name", "CPU(s)", "Vendor ID", "Flags"}
    values = {}
    for line in lscpu.splitlines():
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        if key in wanted:
            values[key.lower().replace(" ", "_").replace("(s)", "s")] = value
    return values


def environment_value(name: str) -> str:
    return os.environ.get(name, "unknown")


def main() -> None:
    args = parse_args()
    raw_dir = args.raw_dir
    measurements = {
        "baseline_fp16": measurement(raw_dir, "baseline-fp16"),
        "baseline_q4_0": measurement(raw_dir, "baseline-q4"),
        "optimized_q4_0_kleidiai": measurement(raw_dir, "kleidiai-q4"),
    }
    fp16 = measurements["baseline_fp16"]
    q4 = measurements["baseline_q4_0"]
    optimized = measurements["optimized_q4_0_kleidiai"]

    activation_log = (raw_dir / "kleidiai-activation.log").read_text(errors="replace")
    activation_lines = [
        line.strip()
        for line in activation_log.splitlines()
        if "kleidiai" in line.lower() and ("kernel" in line.lower() or "buffer" in line.lower())
    ]
    primary_kernel = any("primary q4 kernel feature" in line.lower() for line in activation_lines)
    model_buffer = any(
        "cpu_kleidiai model buffer size" in line.lower() for line in activation_lines
    )
    if not primary_kernel or not model_buffer:
        raise RuntimeError("KleidiAI was compiled but its Q4 inference path was not proven active")

    smoke = {
        label: json.loads((raw_dir / f"smoke-{label}.json").read_text())
        for label in ("baseline-fp16", "kleidiai-q4")
    }
    if not all(all(item["quality_gate"].values()) for item in smoke.values()):
        raise RuntimeError("FP16 or optimized Q4_0 failed the Cloud Steward safety-quality gate")

    lscpu = (raw_dir / "lscpu.txt").read_text(errors="replace")
    evidence = {
        "schema_version": 1,
        "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "environment": {
            "runner": os.getenv("RUNNER_NAME", "native-arm64"),
            "runner_image": environment_value("ImageOS"),
            "runner_image_version": environment_value("ImageVersion"),
            "architecture": platform.machine().lower(),
            "cpu": concise_cpu(lscpu),
            "logical_cpu_count": os.cpu_count(),
        },
        "software": {
            "llama_cpp_commit": LLAMA_CPP_COMMIT,
            "baseline_backend": "llama.cpp CPU",
            "optimized_backend": "llama.cpp CPU with Arm KleidiAI",
            "kleidiai_active": True,
            "kleidiai_activation_evidence": activation_lines[:8],
        },
        "models": {
            "repository": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
            "revision": MODEL_REVISION,
            "license": "Apache-2.0",
            "fp16_sha256": MODEL_HASHES["fp16"],
            "q4_0_sha256": MODEL_HASHES["q4_0"],
        },
        "method": {
            "native_arm64": True,
            "cpu_only": True,
            "repetitions": 5,
            "prompt_tokens": 512,
            "generation_tokens": 128,
            "load_mode": "none",
            "quality_gate": "Same Cloud Steward schema and safety assertions for FP16 and Q4_0",
        },
        "measurements": measurements,
        "comparisons": {
            "q4_0_vs_fp16": {
                "model_size_reduction_percent": reduction(
                    q4["model_size_bytes"], fp16["model_size_bytes"]
                ),
                "peak_rss_reduction_percent": reduction(q4["peak_rss_kib"], fp16["peak_rss_kib"]),
                "prompt_speedup": speedup(
                    q4["prompt_tokens_per_second"], fp16["prompt_tokens_per_second"]
                ),
                "generation_speedup": speedup(
                    q4["generation_tokens_per_second"],
                    fp16["generation_tokens_per_second"],
                ),
            },
            "kleidiai_vs_q4_0_cpu": {
                "prompt_speedup": speedup(
                    optimized["prompt_tokens_per_second"], q4["prompt_tokens_per_second"]
                ),
                "generation_speedup": speedup(
                    optimized["generation_tokens_per_second"],
                    q4["generation_tokens_per_second"],
                ),
            },
            "optimized_q4_0_vs_fp16": {
                "model_size_reduction_percent": reduction(
                    optimized["model_size_bytes"], fp16["model_size_bytes"]
                ),
                "peak_rss_reduction_percent": reduction(
                    optimized["peak_rss_kib"], fp16["peak_rss_kib"]
                ),
                "prompt_speedup": speedup(
                    optimized["prompt_tokens_per_second"],
                    fp16["prompt_tokens_per_second"],
                ),
                "generation_speedup": speedup(
                    optimized["generation_tokens_per_second"],
                    fp16["generation_tokens_per_second"],
                ),
            },
        },
        "quality": {
            label: item["quality_gate"] for label, item in smoke.items()
        },
        "disclosures": [
            "Measurements describe one ephemeral GitHub-hosted Arm64 VM, not every Arm CPU.",
            (
                "Q4_0 changes numeric precision; parity here means both plans passed "
                "identical structural safety gates, not identical prose."
            ),
            "The public Render demo remains x86_64 and does not use this local inference path.",
        ],
    }
    if evidence["environment"]["architecture"] not in {"aarch64", "arm64"}:
        raise RuntimeError("Refusing to publish an Arm benchmark captured on another architecture")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(evidence, indent=2) + "\n").encode()
    args.output.write_bytes(content)
    args.output.with_suffix(f"{args.output.suffix}.sha256").write_text(
        f"{hashlib.sha256(content).hexdigest()}  {args.output.name}\n",
        encoding="utf-8",
    )
    comparison = evidence["comparisons"]["optimized_q4_0_vs_fp16"]
    kleidiai = evidence["comparisons"]["kleidiai_vs_q4_0_cpu"]
    fp16_row = (
        f"| FP16 CPU baseline | {fp16['prompt_tokens_per_second']:.3f} | "
        f"{fp16['generation_tokens_per_second']:.3f} | {fp16['peak_rss_kib'] / 1024:.1f} |"
    )
    q4_row = (
        f"| Q4_0 CPU baseline | {q4['prompt_tokens_per_second']:.3f} | "
        f"{q4['generation_tokens_per_second']:.3f} | {q4['peak_rss_kib'] / 1024:.1f} |"
    )
    optimized_row = (
        f"| Q4_0 + KleidiAI | {optimized['prompt_tokens_per_second']:.3f} | "
        f"{optimized['generation_tokens_per_second']:.3f} | "
        f"{optimized['peak_rss_kib'] / 1024:.1f} |"
    )
    comparison_text = (
        f"Optimized Q4_0 reduced model size by "
        f"**{comparison['model_size_reduction_percent']:.2f}%** and peak RSS by "
        f"**{comparison['peak_rss_reduction_percent']:.2f}%** versus FP16. It delivered "
        f"**{comparison['prompt_speedup']:.3f}x** prompt throughput and "
        f"**{comparison['generation_speedup']:.3f}x** generation throughput. KleidiAI "
        f"contributed **{kleidiai['prompt_speedup']:.3f}x** prompt and "
        f"**{kleidiai['generation_speedup']:.3f}x** generation throughput versus the "
        "same Q4_0 model on the regular CPU backend."
    )
    quality_text = (
        "Both FP16 and optimized Q4_0 generated a Cloud Steward plan that passed the same "
        "dry-run, approval, verification, rollback, risk, and proposal-only gates. Results "
        "are specific to this recorded runner; see the JSON evidence for methodology and "
        "disclosures."
    )
    markdown = f"""# Native Arm64 inference benchmark

- Architecture: `{evidence['environment']['architecture']}`
- CPU: `{evidence['environment']['cpu'].get('model_name', 'unknown')}`
- llama.cpp: `{LLAMA_CPP_COMMIT}`
- Model: Qwen2.5-0.5B-Instruct, FP16 and Q4_0
- KleidiAI Q4 path verified: **yes**

| Configuration | Prompt tok/s | Generation tok/s | Peak RSS MiB |
| --- | ---: | ---: | ---: |
{fp16_row}
{q4_row}
{optimized_row}

{comparison_text}

{quality_text}
"""
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(markdown, encoding="utf-8")
    print(json.dumps(evidence["comparisons"], indent=2))


if __name__ == "__main__":
    main()