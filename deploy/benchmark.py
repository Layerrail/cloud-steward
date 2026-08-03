import json
import platform
import statistics
import time
from pathlib import Path

from cloud_steward.datahub import DataHubContextProvider
from cloud_steward.models import PlanRequest
from cloud_steward.planner import PlanGenerator

REQUEST = PlanRequest(
    goal="Protect invoice generation while diagnosing checkout latency",
    context_query="checkout billing invoice production",
)
CONTEXT = DataHubContextProvider._sample(REQUEST.context_query)


def run(iterations: int = 1000) -> dict:
    samples = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        PlanGenerator._deterministic_plan(REQUEST, CONTEXT)
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    ordered = sorted(samples)
    result = {
        "architecture": platform.machine().lower(),
        "python": platform.python_version(),
        "iterations": iterations,
        "median_ms": round(statistics.median(samples), 4),
        "p95_ms": round(ordered[int(iterations * 0.95) - 1], 4),
        "mean_ms": round(statistics.mean(samples), 4),
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/benchmark.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
