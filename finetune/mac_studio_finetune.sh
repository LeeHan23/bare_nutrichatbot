#!/usr/bin/env bash
# Fine-tune Qwen on the Mac Studio (M3 Ultra) with mlx-lm and register the
# result in Ollama as a *candidate* tag. Production (qwen2.5:32b) keeps serving
# throughout and is never touched; promotion is a .env change on the Han
# Server, only after the eval gate (finetune/QWEN_FINETUNE.md, "Gating").
#
#   bash finetune/mac_studio_finetune.sh            # all stages
#   bash finetune/mac_studio_finetune.sh train      # one stage: setup train check fuse gguf ollama
#
# Every stage skips itself if its output already exists, so rerunning after an
# interruption resumes. To redo a stage, delete its output under runs/$RUN/.
#
# Knobs (env vars): RUN, DATA, BASE_MLX/BASE_OLLAMA (must be the same model —
# see QWEN_FINETUNE.md "Upgrading the base model"), ITERS, NUM_LAYERS, MAX_SEQ.
set -euo pipefail

RUN=${RUN:-v3}
DATA=${DATA:-finetune/data_mlx_v3}
BASE_MLX=${BASE_MLX:-mlx-community/Qwen2.5-32B-Instruct-4bit}
BASE_OLLAMA=${BASE_OLLAMA:-qwen2.5:32b}  # chat template + parameters are copied from this tag
ITERS=${ITERS:-200}
NUM_LAYERS=${NUM_LAYERS:-16}
MAX_SEQ=${MAX_SEQ:-6144}  # live prompts are ~10-11k chars (~3-4k tokens), longer in BM
REPO=${REPO:-$HOME/nutribot-finetune}
VENV=${VENV:-$HOME/mlx-finetune-env}
LLAMA_CPP=${LLAMA_CPP:-$HOME/llama.cpp}

TAG=nutribot-qwen-lora-$RUN
OUT=$REPO/finetune/runs/$RUN
STAGE=${1:-all}

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
skip() { echo "   skip: $1 exists"; }
want() { [[ $STAGE == all || $STAGE == "$1" ]]; }

if want setup; then
  say "setup"
  if [[ -d $REPO/.git ]]; then git -C "$REPO" pull --ff-only
  else git clone https://github.com/LeeHan23/bare_nutrichatbot.git "$REPO"; fi
  [[ -f $REPO/$DATA/train.jsonl && -f $REPO/$DATA/valid.jsonl ]] \
    || { echo "missing $REPO/$DATA/{train,valid}.jsonl — push it from the Han Server or copy it over (USB/scp)"; exit 1; }
  wc -l "$REPO/$DATA"/*.jsonl

  [[ -d $VENV ]] || python3 -m venv "$VENV"
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
  pip install -q -U "mlx-lm[train]"

  if [[ ! -x $LLAMA_CPP/build/bin/llama-quantize ]]; then
    command -v cmake >/dev/null || { echo "cmake missing: brew install cmake"; exit 1; }
    [[ -d $LLAMA_CPP ]] || git clone --depth 1 https://github.com/ggml-org/llama.cpp "$LLAMA_CPP"
    cmake -S "$LLAMA_CPP" -B "$LLAMA_CPP/build" -DCMAKE_BUILD_TYPE=Release
    cmake --build "$LLAMA_CPP/build" -j --target llama-quantize
  fi
  pip install -q -r "$LLAMA_CPP/requirements/requirements-convert_hf_to_gguf.txt"

  # Flags the mlx-lm docs don't list — fail now, not two hours in.
  for f in --max-seq-length --mask-prompt --grad-checkpoint; do
    mlx_lm.lora --help | grep -q -- "$f" || { echo "mlx_lm.lora has no $f — check mlx_lm.lora --help"; exit 1; }
  done
  mlx_lm.fuse --help | grep -q -- --de-quantize || { echo "mlx_lm.fuse has no --de-quantize"; exit 1; }

  # Peak disk: ~20GB base download + ~65GB fused fp16 + ~65GB f16 GGUF + ~20GB Q4.
  free_gb=$(df -g "$HOME" | awk 'NR==2 {print $4}')
  echo "   free disk: ${free_gb}GB"
  (( free_gb >= 180 )) || { echo "need ~180GB free"; exit 1; }
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"
mkdir -p "$OUT"

if want train; then
  say "train $RUN on $DATA ($ITERS iters)"
  if [[ -f $OUT/adapter/adapters.safetensors ]]; then skip "$OUT/adapter"
  else
    # Ollama (~31GB) and CLaRa stay loaded, so live chat keeps working but slows
    # down. If memory_pressure shows red, raise the GPU wired limit
    # (sudo sysctl iogpu.wired_limit_mb=86000) or, if CLaRa is off in
    # production (CLARA_COMPRESS_DOC_LIMIT=0), stop it:
    # sudo launchctl bootout system/com.nutribot.clara
    memory_pressure | tail -1
    # --mask-prompt: loss on the reply only. Review examples are ~3-4k prompt
    # tokens + ~300 reply tokens; unmasked, the prompt would drown the correction.
    mlx_lm.lora --model "$BASE_MLX" --train --data "$REPO/$DATA" \
      --iters "$ITERS" --batch-size 1 --num-layers "$NUM_LAYERS" \
      --max-seq-length "$MAX_SEQ" --mask-prompt --grad-checkpoint \
      --adapter-path "$OUT/adapter" 2>&1 | tee "$OUT/train.log"
  fi
fi

if want check; then
  say "sanity check: adapter vs training target on 3 review prompts"
  # Read the output by eye before spending ~1h on fuse/convert. If the reply
  # still hedges where the target refutes, change ITERS/data, not the gate.
  python - "$BASE_MLX" "$OUT/adapter" "$REPO/$DATA/train.jsonl" <<'PY' | tee "$OUT/check.txt"
import json, sys
from mlx_lm import load, generate
base, adapter, data = sys.argv[1:]
recs = [r for r in map(json.loads, open(data)) if len(r["messages"]) == 2][:3]
model, tok = load(base, adapter_path=adapter)
for r in recs:
    user, target = r["messages"]
    prompt = tok.apply_chat_template([user], add_generation_prompt=True, tokenize=False)
    print("QUESTION:", user["content"].rsplit("## Question", 1)[-1].split("## Answer")[0].strip())
    print("\nADAPTER:", generate(model, tok, prompt=prompt, max_tokens=300))
    print("\nTARGET:", target["content"], "\n" + "-" * 70)
PY
fi

if want fuse; then
  say "fuse (de-quantized, so llama.cpp can read it)"
  if [[ -f $OUT/fused/config.json ]]; then skip "$OUT/fused"
  else mlx_lm.fuse --model "$BASE_MLX" --adapter-path "$OUT/adapter" --save-path "$OUT/fused" --de-quantize; fi
fi

if want gguf; then
  say "GGUF Q4_K_M (same quantization as production)"
  if [[ -f $OUT/q4_k_m.gguf ]]; then skip "$OUT/q4_k_m.gguf"
  else
    [[ -f $OUT/f16.gguf ]] || python "$LLAMA_CPP/convert_hf_to_gguf.py" "$OUT/fused" --outfile "$OUT/f16.gguf" --outtype f16
    "$LLAMA_CPP/build/bin/llama-quantize" "$OUT/f16.gguf" "$OUT/q4_k_m.gguf" Q4_K_M
  fi
fi

if want ollama; then
  say "ollama create $TAG"
  # Same TEMPLATE/stop/params as production, so the weights are the only difference.
  ollama show "$BASE_OLLAMA" --modelfile | sed "s|^FROM .*|FROM $OUT/q4_k_m.gguf|" > "$OUT/Modelfile"
  ollama create "$TAG" -f "$OUT/Modelfile"
  ollama run "$TAG" "Reply with one short sentence confirming you are online."
  cat <<EOF

Done: Ollama tag $TAG. Next, on the Han Server (QWEN_FINETUNE.md "Gating promotion"):
  OLLAMA_MODEL=$TAG .venv/bin/python eval/test_rag.py --out eval/results/rag_candidate_$RUN.json
Once the tag works, free ~130GB with: rm -rf "$OUT/fused" "$OUT/f16.gguf"
EOF
fi
