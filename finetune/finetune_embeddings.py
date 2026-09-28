"""
finetune_embeddings.py

LoRA fine-tuning for medical nutrition retrieval using sentence-transformers 3.x + PEFT.

Two model options:
  --model bge-m3   (DEFAULT) Fine-tune BAAI/bge-m3 (570M, encoder, ~30-60 min on RTX 3050)
                   Already downloaded, already in production — no re-index headache.
  --model gte      Fine-tune Alibaba-NLP/gte-Qwen2-1.5B-instruct (1.5B, decoder, ~40 hrs)
                   Higher ceiling but impractical without an A100.

Hardware target: RTX 3050 4GB VRAM
  bge-m3 FP16: ~1.1 GB base + ~400 MB activations (batch 16) = ~1.5 GB — very comfortable
  gte QLoRA:   ~1.5 GB base + ~400 MB activations (batch 2) = ~2 GB — tight

Outputs:
  ~/models/embedding_lora/    — LoRA adapter weights + nutribot_adapter_config.json

Usage:
    python finetune_embeddings.py                   # bge-m3, recommended
    python finetune_embeddings.py --model gte       # gte-Qwen2-1.5B (slow)
    python finetune_embeddings.py --max-pairs 5000  # quick test run (~5 min)
    python finetune_embeddings.py --epochs 1        # single epoch
    python finetune_embeddings.py --dry-run         # verify setup, no training
"""

import argparse
import json
import os
import sys

os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# ---------------------------------------------------------------------------
# Model profiles
# ---------------------------------------------------------------------------
MODELS = {
    "bge-m3": {
        "name": "BAAI/bge-m3",
        "pooling": "mean",
        "lora_targets": ["query", "value"],
        "use_qlora": False,
        "batch_size": 8,
        "grad_accum": 4,       # effective batch = 32
        "max_seq_len": 256,
        "fp16": False,
        "bf16": True,
        "download_size": "~2.3 GB",
    },
    "gte": {
        "name": "Alibaba-NLP/gte-Qwen2-1.5B-instruct",
        "pooling": "lasttoken",
        "lora_targets": ["q_proj", "v_proj"],
        "use_qlora": True,
        "batch_size": 2,
        "grad_accum": 8,       # effective batch = 16
        "max_seq_len": 256,
        "fp16": False,
        "bf16": True,          # avoids FP16 GradScaler conflict with QLoRA
        "download_size": "~3 GB",
    },
}

ADAPTER_OUTPUT_DIR = os.path.expanduser("~/models/embedding_lora")
TRAIN_FILE = os.path.expanduser("~/data/embedding_train.jsonl")
VAL_FILE = os.path.expanduser("~/data/embedding_val.jsonl")

LORA_RANK = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
LEARNING_RATE = 2e-4
NUM_EPOCHS = 3
WARMUP_RATIO = 0.1

GTE_QUERY_PREFIX = (
    "Instruct: Given a medical nutrition question, "
    "retrieve relevant passages that answer the question\nQuery: "
)


def load_jsonl(path: str, max_pairs: int | None = None) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
                if max_pairs and len(records) >= max_pairs:
                    break
    return records


def check_dependencies():
    missing = []
    for pkg in ["torch", "transformers", "peft", "sentence_transformers", "datasets"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        sys.exit(
            f"Missing packages: {', '.join(missing)}\n"
            "Install: pip install torch transformers peft sentence-transformers datasets bitsandbytes accelerate"
        )


def build_dataset(train_records, val_records, add_query_prefix: bool):
    from datasets import Dataset

    def to_dict(records):
        prefix = GTE_QUERY_PREFIX if add_query_prefix else ""
        return {
            "anchor":   [prefix + r["anchor"] for r in records],
            "positive": [r["positive"] for r in records],
        }

    return Dataset.from_dict(to_dict(train_records)), Dataset.from_dict(to_dict(val_records))


def run_training(profile: dict, num_epochs: int, dry_run: bool, max_pairs: int | None):
    import torch
    from peft import LoraConfig, TaskType, get_peft_model
    from sentence_transformers import (
        SentenceTransformer,
        SentenceTransformerTrainer,
        SentenceTransformerTrainingArguments,
    )
    from sentence_transformers.losses import MultipleNegativesRankingLoss
    from sentence_transformers.models import Pooling, Transformer
    from sentence_transformers.training_args import BatchSamplers
    from transformers import AutoModel, AutoTokenizer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model_name = profile["name"]

    print(f"Device: {device}")
    if device == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}  |  VRAM: {torch.cuda.get_device_properties(0).total_memory/1e9:.1f} GB")

    print(f"\nModel:   {model_name}")
    print(f"Pooling: {profile['pooling']}  |  LoRA targets: {profile['lora_targets']}")
    print(f"Batch:   {profile['batch_size']} × {profile['grad_accum']} accum = {profile['batch_size']*profile['grad_accum']} effective")
    print(f"QLoRA:   {profile['use_qlora']}")

    # -----------------------------------------------------------------------
    # Load base model
    # -----------------------------------------------------------------------
    print(f"\nLoading base model ({profile['download_size']} on first run)...")

    load_kwargs = dict(trust_remote_code=True)

    if profile["use_qlora"] and device == "cuda":
        from transformers import BitsAndBytesConfig
        compute_dtype = torch.bfloat16 if profile["bf16"] else torch.float32
        load_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_use_double_quant=True,
        )
        load_kwargs["device_map"] = "auto"
    elif device == "cuda":
        load_kwargs["torch_dtype"] = torch.bfloat16 if profile["bf16"] else torch.float16
        load_kwargs["device_map"] = "auto"

    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    base_hf_model = AutoModel.from_pretrained(model_name, **load_kwargs)
    base_hf_model.enable_input_require_grads()

    # -----------------------------------------------------------------------
    # Attach LoRA
    # -----------------------------------------------------------------------
    lora_config = LoraConfig(
        task_type=TaskType.FEATURE_EXTRACTION,
        r=LORA_RANK,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=profile["lora_targets"],
        bias="none",
    )
    peft_model = get_peft_model(base_hf_model, lora_config)
    peft_model.print_trainable_parameters()

    if dry_run:
        print("\nDry run complete — model loads and LoRA attaches successfully.")
        print(f"Adapter would save to: {ADAPTER_OUTPUT_DIR}")
        return

    # -----------------------------------------------------------------------
    # Wrap in SentenceTransformer
    # Transformer() loads the model a second time; we immediately replace it
    # with our LoRA model and free the duplicate to avoid a double-VRAM hit.
    # -----------------------------------------------------------------------
    import gc
    word_embedding_model = Transformer(
        model_name,
        max_seq_length=profile["max_seq_len"],
        tokenizer_name_or_path=model_name,
    )
    del word_embedding_model.auto_model   # drop the freshly loaded duplicate
    word_embedding_model.auto_model = peft_model
    gc.collect()
    torch.cuda.empty_cache()

    pooling_kwargs = {}
    if profile["pooling"] == "mean":
        pooling_kwargs["pooling_mode_mean_tokens"] = True
    else:
        pooling_kwargs["pooling_mode_lasttoken"] = True

    pooling_model = Pooling(
        word_embedding_model.get_word_embedding_dimension(),
        **pooling_kwargs,
    )
    st_model = SentenceTransformer(modules=[word_embedding_model, pooling_model])

    # -----------------------------------------------------------------------
    # Dataset + loss
    # -----------------------------------------------------------------------
    print("\nLoading training data...")
    train_val_limit = int(max_pairs * 0.9) if max_pairs else None
    val_limit = max_pairs - train_val_limit if max_pairs else None
    train_records = load_jsonl(TRAIN_FILE, train_val_limit)
    val_records = load_jsonl(VAL_FILE, val_limit)
    print(f"  Train: {len(train_records):,} pairs | Val: {len(val_records):,} pairs")

    add_prefix = profile["pooling"] == "lasttoken"
    train_ds, val_ds = build_dataset(train_records, val_records, add_prefix)
    loss = MultipleNegativesRankingLoss(st_model)

    # Rough ETA
    steps_per_epoch = len(train_records) // profile["batch_size"]
    total_steps = steps_per_epoch * num_epochs
    secs_per_step = 0.25 if profile["pooling"] == "mean" else 12.5
    eta_min = total_steps * secs_per_step / 60
    print(f"  Estimated time: ~{eta_min:.0f} min ({total_steps:,} steps @ ~{secs_per_step}s/step)")

    # -----------------------------------------------------------------------
    # Training arguments
    # -----------------------------------------------------------------------
    os.makedirs(ADAPTER_OUTPUT_DIR, exist_ok=True)
    train_args = SentenceTransformerTrainingArguments(
        output_dir=ADAPTER_OUTPUT_DIR,
        num_train_epochs=num_epochs,
        per_device_train_batch_size=profile["batch_size"],
        per_device_eval_batch_size=profile["batch_size"],
        gradient_accumulation_steps=profile["grad_accum"],
        learning_rate=LEARNING_RATE,
        warmup_ratio=WARMUP_RATIO,
        fp16=profile["fp16"] and device == "cuda",
        bf16=profile["bf16"] and device == "cuda",
        batch_sampler=BatchSamplers.NO_DUPLICATES,
        eval_strategy="steps",
        eval_steps=max(50, steps_per_epoch // 5),
        save_strategy="steps",
        save_steps=max(50, steps_per_epoch // 5),
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        logging_steps=max(10, steps_per_epoch // 20),
        dataloader_num_workers=0,
        report_to="none",
    )

    trainer = SentenceTransformerTrainer(
        model=st_model,
        args=train_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        loss=loss,
    )

    print(f"\nStarting training...")
    trainer.train()

    # -----------------------------------------------------------------------
    # Save
    # -----------------------------------------------------------------------
    print(f"\nSaving LoRA adapter to {ADAPTER_OUTPUT_DIR}...")
    peft_model.save_pretrained(ADAPTER_OUTPUT_DIR)
    tokenizer.save_pretrained(ADAPTER_OUTPUT_DIR)

    cfg = {
        "base_model": model_name,
        "max_seq_len": profile["max_seq_len"],
        "pooling": profile["pooling"],
    }
    with open(os.path.join(ADAPTER_OUTPUT_DIR, "nutribot_adapter_config.json"), "w") as f:
        json.dump(cfg, f, indent=2)

    print(f"Done. Adapter saved to: {ADAPTER_OUTPUT_DIR}")
    print("Add EMBEDDING_ADAPTER_PATH=~/models/embedding_lora to .env, then restart.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["bge-m3", "gte"], default="bge-m3",
                        help="Base model to fine-tune (default: bge-m3, fast)")
    parser.add_argument("--epochs", type=int, default=NUM_EPOCHS)
    parser.add_argument("--max-pairs", type=int, default=None,
                        help="Cap total training pairs (e.g. 5000 for a quick test)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Load model and verify setup without training")
    args = parser.parse_args()

    check_dependencies()

    if not args.dry_run:
        for path in [TRAIN_FILE, VAL_FILE]:
            if not os.path.exists(path):
                sys.exit(
                    f"Training data not found: {path}\n"
                    "Run: python generate_embedding_training_data.py --provider ollama"
                )

    profile = MODELS[args.model]
    run_training(profile, num_epochs=args.epochs, dry_run=args.dry_run, max_pairs=args.max_pairs)


if __name__ == "__main__":
    main()
