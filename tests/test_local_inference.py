import json
from types import SimpleNamespace

import pytest

from cloud_steward.datahub import DataHubContextProvider
from cloud_steward.local_inference import LlamaCppPlanner
from cloud_steward.models import PlanRequest, RiskLevel
from cloud_steward.planner import PlanGenerator
from cloud_steward.settings import Settings


def local_plan_json() -> str:
    return json.dumps(
        {
            "summary": "Inspect context and prepare a reversible change.",
            "assumptions": ["Governed metadata must be verified before use."],
            "context_findings": ["The governed checkout dataset has a named owner."],
            "actions": [
                {
                    "action": "Inspect health",
                    "target": "urn:li:dataset:checkout",
                    "reason": "Confirm current state.",
                    "expected_result": "A current health snapshot.",
                    "verification": "Compare health and revision timestamps.",
                    "rollback": "No rollback is required for a read-only action.",
                    "risk": "low",
                    "mutation": False,
                },
                {
                    "action": "Simulate scaling",
                    "target": "urn:li:dataset:checkout",
                    "reason": "Bound downstream impact.",
                    "expected_result": "A dry-run diff.",
                    "verification": "Review affected resources.",
                    "rollback": "Discard the diff.",
                    "risk": "medium",
                    "mutation": False,
                },
                {
                    "action": "Request approval",
                    "target": "production",
                    "reason": "Record accountable authorization.",
                    "expected_result": "A named approval receipt.",
                    "verification": "Verify identity, scope, and plan hash.",
                    "rollback": "Reject or expire the proposal.",
                    "risk": "low",
                    "mutation": True,
                },
            ],
        }
    )


def test_llama_cpp_parser_extracts_first_complete_object() -> None:
    output = f"backend log {{not-json}}\n{local_plan_json()}\n<|im_end|>"

    parsed = LlamaCppPlanner._first_json_object(output)

    assert parsed["actions"][0]["action"] == "Inspect health"


def test_llama_cpp_command_is_cpu_only_and_schema_constrained() -> None:
    planner = LlamaCppPlanner(
        Settings(
            llama_cpp_binary="/opt/llama-cli",
            llama_cpp_model_path="/models/qwen-q4.gguf",
            llama_cpp_threads=4,
        )
    )

    command = planner._command("Plan safely")

    assert command[0] == "/opt/llama-cli"
    assert command[command.index("--model") + 1] == "/models/qwen-q4.gguf"
    assert command[command.index("--device") + 1] == "none"
    assert command[command.index("--n-gpu-layers") + 1] == "0"
    assert command[command.index("--threads") + 1] == "4"
    assert "--conversation" in command
    assert "--single-turn" in command
    assert "--no-warmup" in command
    schema = json.loads(command[command.index("--json-schema") + 1])
    assert schema["properties"]["actions"]["minItems"] == 3


def test_llama_cpp_missing_json_reports_bounded_runtime_diagnostics(monkeypatch) -> None:
    settings = Settings(
        llama_cpp_binary="/opt/llama-cli",
        llama_cpp_model_path="/models/qwen-q4.gguf",
    )
    request = PlanRequest(
        goal="Protect checkout while preparing a capacity change",
        context_query="checkout production",
    )
    context = DataHubContextProvider._sample(request.context_query)
    diagnostic = "runtime diagnostic: no tokens were generated"

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(stdout="", stderr=diagnostic, returncode=0)

    monkeypatch.setattr("cloud_steward.local_inference.subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match=diagnostic):
        LlamaCppPlanner(settings).generate(request, context)


@pytest.mark.asyncio
async def test_local_inference_plan_retains_guardrails(monkeypatch) -> None:
    settings = Settings(
        llama_cpp_binary="/opt/llama-cli",
        llama_cpp_model_path="/models/qwen-q4.gguf",
    )
    request = PlanRequest(
        goal="Protect checkout while preparing a capacity change",
        context_query="checkout production",
    )
    context = DataHubContextProvider._sample(request.context_query)

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(stdout=local_plan_json(), stderr="", returncode=0)

    monkeypatch.setattr("cloud_steward.local_inference.subprocess.run", fake_run)

    plan = await PlanGenerator(settings).generate(request, context)

    assert plan.goal == request.goal
    assert plan.requires_approval is True
    assert [action.order for action in plan.actions] == [1, 2, 3]
    assert plan.actions[-1].mutation is True
    assert plan.actions[-1].risk == RiskLevel.high
    assert plan.overall_risk == RiskLevel.high
    assert "no infrastructure mutation has executed" in " ".join(plan.assumptions).lower()