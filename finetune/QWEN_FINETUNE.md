# Fine-tuning qwen2.5:32b (Part C of the eval/architecture roadmap)

Per the decision recorded in `docs/eval_and_roadmap.md` Part C: fine-tuning targets **`qwen2.5:32b` directly** — the actual production generation model (Option B's Qwen-generate step) — not the existing Gemma-3 experiment track (`finetune/Modelfile`, `finetune/colab_finetune.ipynb`). That track can continue separately if there's ever a reason to ship a smaller/cheaper model, but it doesn't improve what's in production today.

This file documents the recommended approach and starting configuration. It is **not** a runnable training script — actually running a 32B LoRA/QLoRA job needs real GPU time (the Mac Studio's M3 Ultra, or a cloud GPU) that isn't available in the session that wrote this, so the config below is a documented starting point to verify empirically, not a promise it's already tuned.

**Correction (2026-07-17): the framework recommendation below (Unsloth + bitsandbytes QLoRA) does not work on the Mac Studio.** Unsloth depends on Triton/CUDA and has no real Apple Silicon support as of this date (MLX support is in early development upstream, not GA). `bitsandbytes` 4-bit quantization on MPS is also not solid — only a community package, not upstream support. The framework section below has been corrected to use **Apple's own MLX / `mlx-lm`**, which has native LoRA fine-tuning, first-class Qwen2 support, and pre-quantized Qwen2.5 checkpoints on Hugging Face (`mlx-community/Qwen2.5-32B-Instruct-4bit`) — this is the actually-viable path on an M3 Ultra today. The pipeline stages (merge → GGUF → Ollama → eval gate) are unchanged, just the training-framework step.

## Pipeline overview

```
eval/test_rag.py --out results/rag_baseline.json          (Part A: know what's currently failing)
        │
        ▼
finetune/generate_training_data.py --focus-results ...     (Part C: oversample the failing combos)
        │  → data/train.jsonl + data/val.jsonl  (ShareGPT format)
        ▼
QLoRA fine-tune of Qwen2.5-32B-Instruct (this doc)
        │  → LoRA adapter
        ▼
Merge adapter into base weights → convert/quantize to GGUF (llama.cpp)
        │
        ▼
Ollama Modelfile → `ollama create nutribot-qwen-lora -f Modelfile`
        │
        ▼
eval/test_rag.py --out results/rag_candidate.json  (against the new model)
        │
        ▼
scripts/compare_eval_runs.py --baseline ... --candidate ...   (Part C: gate promotion)
        │
        ▼
Only if PROMOTE: point OLLAMA_MODEL at the new tag in .env
```

## Why MLX, not Unsloth/bitsandbytes, for this model

Qwen2.5-32B-Instruct at bf16 is ~64GB of weights alone — on the Mac Studio's 96GB unified memory that leaves little room for activations, gradients, and a usable batch size/context length. 4-bit quantization brings the base weights down to ~18-20GB, leaving generous headroom. Unsloth (the framework `colab_finetune.ipynb` uses for the separate Gemma-3 track) requires CUDA/Triton and does not run on Apple Silicon; `bitsandbytes` quantization on MPS has no solid upstream support either. **MLX** — Apple's own array/ML framework — is the native, actually-working alternative on an M-series Mac: `mlx-lm` ships a first-class `mlx_lm.lora` command, explicit Qwen2 architecture support, and pre-quantized Qwen2.5 checkpoints already published to Hugging Face under the `mlx-community` org.

## Recommended starting configuration

Base model: `mlx-community/Qwen2.5-32B-Instruct-4bit` (Hugging Face, MLX format, auto-downloads on first `mlx_lm.lora` run — **not** the Ollama GGUF already in `/api/tags`, which is a llama.cpp-format Q4_K_M meant for inference, not training).

Framework: [MLX-LM](https://github.com/ml-explore/mlx-lm) (`pip install mlx-lm`, separate venv from the existing `clara` conda env).

```bash
# Starting point -- verify against actual eval results before trusting these values.
mlx_lm.lora --model mlx-community/Qwen2.5-32B-Instruct-4bit --train \
    --data <dir with train.jsonl + valid.jsonl>  \
    --iters 200          # start conservative -- the focus-weighted dataset from
                         # generate_training_data.py --focus-results is small
                         # (e.g. 20 examples) and repeats a narrow set of combos
                         # heavily -- more iterations risks overfitting to exact
                         # phrasing rather than generalizing the stance
    --batch-size 1
    --num-layers 16      # LoRA applied to the last N transformer layers;
                         # mlx-lm default, raise toward all layers if 16 underfits
    --adapter-path <path to save the LoRA adapter>
```

**Data format gotcha**: `mlx_lm.lora` expects a directory containing `train.jsonl` and **`valid.jsonl`** (not `val.jsonl`) with one `{"messages": [{"role": ..., "content": ...}, ...]}` object per line — reshape `generate_training_data.py`'s `{"conversations": [...]}` ShareGPT-format output (rename the key, rename the file) before pointing `--data` at it.

## Data

Use `finetune/generate_training_data.py` with `--focus-results` pointed at the latest `eval/test_rag.py --out` run (see `docs/eval_and_roadmap.md` Part C item 2 for the mechanism — it reads failing `contraindication_check` cases and oversamples conversations that explicitly demonstrate the correct RESTRICT/MODERATE/PERMIT stance for each weak combo). Combine this focus-weighted set with a healthy `--count` of uniform background examples so the model doesn't just memorize the narrow set of corrected combos at the expense of everything else — the `compare_eval_runs.py` gate (below) is exactly what catches that failure mode if it happens. `--provider ollama` (default) or `--provider anthropic` both work for generation — the OpenAI-only path was removed as a hard dependency.

## Fast-path sanity check before productionizing

Before merging/quantizing/deploying anything, test the raw MLX adapter directly against the target failure cases:

```bash
mlx_lm.generate --model mlx-community/Qwen2.5-32B-Instruct-4bit \
    --adapter-path <path> \
    --prompt "A CKD Stage 3 patient with hypertension asks if they can eat a banana. What do you tell them?"
```

If the targeted contraindication combos don't show the corrected stance here, iterate on training data/iterations before spending time on GGUF conversion and Ollama deployment below.

## After training: merge, quantize, deploy

1. Merge the LoRA adapter into the base weights: `mlx_lm.fuse --model mlx-community/Qwen2.5-32B-Instruct-4bit --adapter-path <adapter path> --save-path <merged output dir>`.
2. Convert the merged checkpoint to GGUF and quantize (llama.cpp's `convert-hf-to-gguf.py`, then `llama-quantize`) — match the existing production quantization level (`Q4_K_M`, per the model's current `/api/tags` metadata) unless there's a specific reason to change it.
3. Write an Ollama Modelfile (same pattern as `finetune/Modelfile`, adjusted for the Qwen chat template and stop tokens instead of Gemma-3's) and `ollama create nutribot-qwen-lora -f Modelfile`.

## Gating promotion (Part C item 3)

Do not point production at the new model until it clears the eval gate:

```bash
python eval/test_rag.py --out eval/results/rag_baseline.json         # current qwen2.5:32b
# ... swap OLLAMA_MODEL to the new tag, restart, or point at a second Ollama instance ...
python eval/test_rag.py --out eval/results/rag_candidate.json        # fine-tuned candidate
python scripts/compare_eval_runs.py \
    --baseline eval/results/rag_baseline.json \
    --candidate eval/results/rag_candidate.json
```

Only promote (flip `OLLAMA_MODEL` in `.env`) on a `PROMOTE` verdict — zero regressions and at least one fixed case. A candidate that fixes the targeted contraindication combos but breaks voice/personalization/other categories should not ship; `compare_eval_runs.py`'s per-tag breakdown makes that visible immediately.

## Embeddings (Part C item 4)

If Part A's retrieval-quality visibility improves enough to surface systematic retrieval misses (currently only `[TopicBoost]` print statements in `vector_store.py`, no persisted signal — a gap noted but not closed in this pass), apply the same closed loop to `finetune/finetune_embeddings.py`: use `finetune/generate_embedding_training_data.py` to mine additional (question, passage) pairs for the specific underperforming topics rather than uniformly re-mining the whole knowledge base. Not built out further here since there's no persisted retrieval-quality signal yet to drive it.
