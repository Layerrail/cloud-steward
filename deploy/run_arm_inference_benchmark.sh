#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${ARM_BENCH_WORK:-$ROOT/var/arm-inference}"
RAW="$ROOT/artifacts/arm-inference/raw"
OUT="$ROOT/artifacts/arm-inference"
LLAMA_COMMIT="1464c62d88f699ec9700c8010bbfdbc603a9efd6"
MODEL_REVISION="9217f5db79a29953eb74d5343926648285ec7e67"
MODEL_BASE="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/$MODEL_REVISION"
FP16="$WORK/models/qwen2.5-0.5b-instruct-fp16.gguf"
Q4="$WORK/models/qwen2.5-0.5b-instruct-q4_0.gguf"
THREADS="${ARM_BENCH_THREADS:-4}"
STAGE="${ARM_BENCH_STAGE:-all}"

if [[ "$(uname -m)" != "aarch64" && "$(uname -m)" != "arm64" ]]; then
  echo "This benchmark must run natively on Arm64." >&2
  exit 1
fi

for command in cmake curl git ninja sha256sum /usr/bin/time; do
  command -v "$command" >/dev/null
done

mkdir -p "$WORK/models" "$RAW" "$OUT"
LLAMA="$WORK/llama.cpp"
BASE_BENCH="$LLAMA/build/base/bin/llama-bench"
BASE_CLI="$LLAMA/build/base/bin/llama-cli"
KLEIDI_BENCH="$LLAMA/build/kleidiai/bin/llama-bench"
KLEIDI_CLI="$LLAMA/build/kleidiai/bin/llama-cli"

if [[ "$STAGE" != "smoke" ]]; then
echo "[arm-bench] Capturing native runner metadata"
lscpu > "$RAW/lscpu.txt"
uname -a > "$RAW/uname.txt"
{
  cmake --version | head -1
  "${CC:-cc}" --version | head -1
  python --version
} > "$RAW/toolchain.txt"

download_model() {
  local filename="$1"
  local destination="$2"
  local sha256="$3"
  if [[ ! -f "$destination" ]]; then
    curl --fail --location --retry 5 --retry-all-errors \
      "$MODEL_BASE/$filename?download=true" --output "$destination"
  fi
  printf '%s  %s\n' "$sha256" "$destination" | sha256sum --check
}

download_model \
  "qwen2.5-0.5b-instruct-fp16.gguf" \
  "$FP16" \
  "8e0ae26000627ed62de0e78e41860af70094558b9d2913385c842a6aa06cf3fc"
download_model \
  "qwen2.5-0.5b-instruct-q4_0.gguf" \
  "$Q4" \
  "7671c0c304e6ce5a7fc577bcb12aba01e2c155cc2efd29b2213c95b18edaf6ed"
echo "[arm-bench] Verified immutable FP16 and Q4_0 model artifacts"

if [[ ! -d "$LLAMA/.git" ]]; then
  rm -rf "$LLAMA"
  git init "$LLAMA"
  git -C "$LLAMA" remote add origin https://github.com/ggml-org/llama.cpp.git
fi
git -C "$LLAMA" fetch --depth 1 origin "$LLAMA_COMMIT"
git -C "$LLAMA" checkout --detach FETCH_HEAD
test "$(git -C "$LLAMA" rev-parse HEAD)" = "$LLAMA_COMMIT"
echo "[arm-bench] Checked out llama.cpp $LLAMA_COMMIT"

CMAKE_ARGS=(
  -G Ninja
  -DCMAKE_BUILD_TYPE=Release
  -DBUILD_SHARED_LIBS=OFF
  -DGGML_NATIVE=ON
  -DGGML_CPU=ON
  -DGGML_CPU_REPACK=ON
  -DGGML_OPENMP=ON
  -DGGML_BLAS=OFF
  -DGGML_LLAMAFILE=OFF
  -DGGML_RPC=OFF
  -DGGML_CUDA=OFF
  -DGGML_HIP=OFF
  -DGGML_VULKAN=OFF
  -DGGML_SYCL=OFF
  -DGGML_CANN=OFF
  -DGGML_OPENCL=OFF
  -DGGML_METAL=OFF
  -DLLAMA_BUILD_COMMON=ON
  -DLLAMA_BUILD_TOOLS=ON
  -DLLAMA_BUILD_SERVER=ON
  -DLLAMA_BUILD_UI=OFF
  -DLLAMA_BUILD_TESTS=OFF
  -DLLAMA_BUILD_EXAMPLES=OFF
  -DLLAMA_BUILD_APP=OFF
)

echo "[arm-bench] Building regular CPU baseline"
cmake -S "$LLAMA" -B "$LLAMA/build/base" "${CMAKE_ARGS[@]}" -DGGML_CPU_KLEIDIAI=OFF
cmake --build "$LLAMA/build/base" --target llama-bench llama-cli --parallel "$THREADS"
echo "[arm-bench] Building Arm KleidiAI backend"
cmake -S "$LLAMA" -B "$LLAMA/build/kleidiai" "${CMAKE_ARGS[@]}" -DGGML_CPU_KLEIDIAI=ON
cmake --build "$LLAMA/build/kleidiai" --target llama-bench llama-cli --parallel "$THREADS"

echo "[arm-bench] Proving runtime KleidiAI Q4 kernel activation"
"$KLEIDI_BENCH" \
  --model "$Q4" --n-prompt 32 --n-gen 1 --repetitions 1 \
  --threads "$THREADS" --device none --n-gpu-layers 0 --output jsonl --verbose \
  > /dev/null 2> >(tee "$RAW/kleidiai-activation.log" >&2)
grep -Eiq 'kleidiai: primary q4 kernel feature' "$RAW/kleidiai-activation.log"
grep -Eiq 'CPU_KLEIDIAI model buffer size' "$RAW/kleidiai-activation.log"
echo "[arm-bench] KleidiAI Q4 activation verified"

run_benchmark() {
  local label="$1"
  local binary="$2"
  local model="$3"
  echo "[arm-bench] Measuring $label"
  /usr/bin/time \
    --format='max_rss_kib=%M elapsed_s=%e exit=%x' \
    --output="$RAW/$label.rss" \
    "$binary" \
      --model "$model" \
      --output jsonl \
      --n-prompt 512 \
      --n-gen 128 \
      --repetitions 5 \
      --threads "$THREADS" \
      --device none \
      --n-gpu-layers 0 \
      --load-mode none \
      --progress \
      > "$RAW/$label.jsonl" \
      2> >(tee "$RAW/$label.stderr" >&2)
  echo "[arm-bench] Completed $label"
}

run_benchmark baseline-fp16 "$BASE_BENCH" "$FP16"
run_benchmark baseline-q4 "$BASE_BENCH" "$Q4"
run_benchmark kleidiai-q4 "$KLEIDI_BENCH" "$Q4"
echo "[arm-bench] Native measurements complete"
fi

if [[ "$STAGE" == "measure" ]]; then
  exit 0
fi

for required in "$BASE_CLI" "$KLEIDI_CLI" "$FP16" "$Q4"; do
  test -f "$required"
done

echo "[arm-bench] Running equivalent Cloud Steward safety-quality smoke tests"
python "$ROOT/deploy/arm_inference_smoke.py" \
  --binary "$BASE_CLI" --model "$FP16" --label baseline-fp16 \
  --threads "$THREADS" --output "$RAW/smoke-baseline-fp16.json"
python "$ROOT/deploy/arm_inference_smoke.py" \
  --binary "$KLEIDI_CLI" --model "$Q4" --label kleidiai-q4 \
  --threads "$THREADS" --output "$RAW/smoke-kleidiai-q4.json"

echo "[arm-bench] Normalizing measurements and checksums"
python "$ROOT/deploy/summarize_arm_inference.py" \
  --raw-dir "$RAW" \
  --output "$OUT/benchmark-summary.json" \
  --markdown "$OUT/benchmark-summary.md"
echo "[arm-bench] Native Arm64 inference evidence complete"