import json

from deploy.summarize_arm_inference import measurement, reduction, speedup


def test_arm_summary_parses_prompt_generation_and_rss(tmp_path) -> None:
    common = {
        "build_commit": "1464c62",
        "model_type": "Qwen2 0.5B F16",
        "model_size": 1_266_425_696,
        "model_n_params": 494_032_768,
        "n_threads": 4,
        "devices": "none",
        "load_mode": "none",
        "stddev_ts": 0.5,
    }
    records = [
        {**common, "n_prompt": 512, "n_gen": 0, "avg_ts": 100.0},
        {**common, "n_prompt": 0, "n_gen": 128, "avg_ts": 20.0},
    ]
    raw = "".join(json.dumps(record) + "\n" for record in records)
    (tmp_path / "baseline-fp16.jsonl").write_text(raw)
    (tmp_path / "baseline-fp16.rss").write_text(
        "max_rss_kib=1500000 elapsed_s=12.5 exit=0\n"
    )

    result = measurement(tmp_path, "baseline-fp16")

    assert result["prompt_tokens_per_second"] == 100.0
    assert result["generation_tokens_per_second"] == 20.0
    assert result["peak_rss_kib"] == 1_500_000
    assert len(result["raw_sha256"]) == 64


def test_arm_comparison_helpers() -> None:
    assert speedup(150, 100) == 1.5
    assert reduction(25, 100) == 75.0