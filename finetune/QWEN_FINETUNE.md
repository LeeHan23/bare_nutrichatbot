# Fine-tuning qwen2.5:32b (Part C of the eval/architecture roadmap)

Per the decision recorded in `docs/eval_and_roadmap.md` Part C: fine-tuning targets **`qwen2.5:32b` directly** — the actual production generation model (Option B's Qwen-generate step) — not the existing Gemma-3 experiment track (`finetune/Modelfile`, `finetune/colab_finetune.ipynb`). That track can continue separately if there's ever a reason to ship a smaller/cheaper model, but it doesn't improve what's in production today.

This file documents the recommended approach and starting configuration. Everything past "## Runbook" below is a concrete, copy-pasteable sequence to run on the Mac Studio itself — the rest of the doc (framework rationale, pipeline diagram) is background, not steps.

## Attempt #1 result (2026-08-11) — DO NOT PROMOTE

A first run of this exact pipeline already happened, on 2026-08-11 — undocumented until 2026-08-18 (see `docs/TRIPOD_LLM_Report.md` Item 6b for the full account, including a correction to an earlier wrong conclusion in that report about what these files were). Result, confirmed via `scripts/compare_eval_runs.py`: **DO NOT PROMOTE, 9 regressions, 0 improvements**, spread across nearly every category rather than concentrated in the targeted contraindication combos. `qwen2.5:32b` in production is unaffected — this never shipped.

**Likely cause**: the training data was `data_focus_v2` (45 targeted examples) + `data_uniform_100` (100 generic examples) — background examples outnumber the targeted stance-correction examples ~2:1. The result was a systematic softening (more PERMIT-first framing) across the board, the opposite of the intended firmer RESTRICT calibration — consistent with the generic majority diluting the targeted minority signal rather than the model failing to learn at all.

**For attempt #2**, the clearest lever to try first: rebalance the mix toward the focus-weighted examples — e.g. regenerate with `finetune/generate_training_data.py --focus-results ... --focus-weight` set higher relative to `--count`, so targeted examples aren't a minority of the training signal. The runbook below is otherwise unchanged and still applies.

## Runbook (ready to execute, 2026-08-18)

Run this on the **Mac Studio** (M3 Ultra), not the RTX 3050 — `mlx-lm` needs Apple Silicon. Steps marked **(RTX 3050)** happen back on this repo's usual box instead.

**0. Get the data onto the Mac Studio.** The Mac Studio's existing clone (`/Users/bing/Desktop/clara_lyh/clara-nutri/`) is CLaRa-inference-only, not this repo — you need `finetune/data_mlx/` from `bare_NutriChatbot`, which is now committed (`origin/main`, commit `95de211`). Either clone the full repo somewhere convenient, or just pull that one directory:
```bash
git clone https://github.com/LeeHan23/bare_nutrichatbot.git ~/nutribot-finetune
cd ~/nutribot-finetune
ls finetune/data_mlx/    # expect train.jsonl (148 examples) and valid.jsonl (17 examples)
```

**1. Set up mlx-lm in its own venv** (separate from the `clara` conda env — don't mix):
```bash
python3 -m venv ~/mlx-finetune-env
source ~/mlx-finetune-env/bin/activate
pip install mlx-lm
df -h ~   # sanity-check free disk before the ~18-20GB base-model download below
```

**2. Run the LoRA fine-tune.** The config below (`--iters 200`, `--num-layers 16`) was originally sized for a hypothetical ~20-example dataset; the real committed set is **148 train / 17 valid examples** (7x larger — `data_focus_v2`'s 45 focus-weighted examples + `data_uniform_100`'s 100 background examples, combined). That's still a reasonable conservative starting point (still small by LLM fine-tuning standards), just don't assume the original "risk of overfitting on ~20 examples repeated a lot" framing still applies unchanged — 200 iters now means less repetition per example than originally planned:
```bash
mlx_lm.lora --model mlx-community/Qwen2.5-32B-Instruct-4bit --train \
    --data ~/nutribot-finetune/finetune/data_mlx \
    --iters 200 \
    --batch-size 1 \
    --num-layers 16 \
    --adapter-path ~/nutribot-finetune/finetune/adapters/qwen25-32b-lora-v1
```
This auto-downloads the ~18-20GB base model on first run — expect that alone to take a while depending on bandwidth.

**3. Fast-path sanity check** before spending time on merge/quantize/deploy:
```bash
mlx_lm.generate --model mlx-community/Qwen2.5-32B-Instruct-4bit \
    --adapter-path ~/nutribot-finetune/finetune/adapters/qwen25-32b-lora-v1 \
    --prompt "A CKD Stage 3 patient with hypertension asks if they can eat a banana. What do you tell them?"
```
Expect a firm RESTRICT/strictly-limit stance (this is exactly the `data_focus_v2` combo the focus-weighted examples targeted). If it still hedges MODERATE here, iterate on iters/data before going further — don't spend time on GGUF conversion yet.

**4. Merge the adapter into the base weights:**
```bash
mlx_lm.fuse --model mlx-community/Qwen2.5-32B-Instruct-4bit \
    --adapter-path ~/nutribot-finetune/finetune/adapters/qwen25-32b-lora-v1 \
    --save-path ~/nutribot-finetune/finetune/merged/qwen25-32b-lora-v1
```

**5. Convert to GGUF and quantize.** Needs `llama.cpp` cloned/built on the Mac Studio (not currently confirmed present — check first, `git clone https://github.com/ggerganov/llama.cpp` if not). Match production's existing quantization, confirmed live from the running Ollama model: `qwen2` family, `Q4_K_M`, ChatML template (`<|im_start|>`/`<|im_end|>`):
```bash
python llama.cpp/convert-hf-to-gguf.py ~/nutribot-finetune/finetune/merged/qwen25-32b-lora-v1 \
    --outfile ~/nutribot-finetune/finetune/nutribot-qwen-lora.gguf --outtype f16
llama.cpp/llama-quantize ~/nutribot-finetune/finetune/nutribot-qwen-lora.gguf \
    ~/nutribot-finetune/finetune/nutribot-qwen-lora.Q4_K_M.gguf Q4_K_M
```

**6. Write an Ollama Modelfile and create the tag.** Unlike `finetune/Modelfile` (Gemma-3, different stop tokens), this needs Qwen2's ChatML stop token:
```
FROM ./nutribot-qwen-lora.Q4_K_M.gguf
PARAMETER temperature 0.5
PARAMETER num_predict 800
PARAMETER stop "<|im_end|>"
```
```bash
ollama create nutribot-qwen-lora -f Modelfile
ollama run nutribot-qwen-lora "test prompt"   # confirm it loads and generates before the eval gate
```

**7. Run the eval gate — (RTX 3050), not the Mac Studio.** `eval/test_rag.py` needs this repo's Postgres/patient data, which only lives on the RTX 3050; it reaches the Mac Studio's Ollama over the existing tunnel. Once the `nutribot-qwen-lora` tag exists (step 6), tell the RTX-3050 session (or run it yourself there) to point at it and re-run the gate — see "Gating promotion" below for the exact commands. **Only flip `OLLAMA_MODEL` in `.env` on a `PROMOTE` verdict.**

**Scope reminder**: this dataset is nutrition-only (single-disease ADIME persona), predating the 2026-08-12/14 multi-component taxonomy work. A successful run here improves the original dietetics persona only — it does not touch the 9 non-nutrition components, which have no training data yet.

---

Everything below this point is background/rationale for the runbook above, not additional steps — actually running a 32B LoRA/QLoRA job needs real GPU time (the Mac Studio's M3 Ultra, or a cloud GPU) that wasn't available in the session that originally wrote this doc, so the config below was a documented starting point to verify empirically, not a promise it was already tuned.

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
