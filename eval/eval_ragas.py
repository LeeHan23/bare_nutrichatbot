"""
RAGAS evaluation for the NutriChatbot RAG pipeline.

Metrics scored:
  - faithfulness      : answer is grounded in retrieved contexts (no hallucination)
  - answer_relevancy  : answer actually addresses the question
  - context_precision : retrieved chunks are relevant to the question
  - context_recall    : retrieved chunks cover the ground-truth answer

Usage:
    python eval_ragas.py                          # all 25 questions
    python eval_ragas.py --limit 5                # quick smoke-test
    python eval_ragas.py --category "Hypertension"
    python eval_ragas.py --out results.json       # save detailed results
"""

import os
import argparse

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Parse --local early so USE_OLLAMA is set before chain_factory / llm.py load
_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--local", action="store_true")
_pre.add_argument("--answer-model", default="adime-final")
_pre_args, _ = _pre.parse_known_args()

if _pre_args.local:
    os.environ["USE_OLLAMA"] = "true"
    os.environ["OLLAMA_MODEL"] = _pre_args.answer_model
    os.environ.setdefault("OPENAI_API_KEY", "not-used")   # suppress llm.py key check

import json
import uuid
import time
from dotenv import load_dotenv

load_dotenv()

from datasets import Dataset
from ragas import evaluate, RunConfig
from ragas.llms import LangchainLLMWrapper
from ragas.metrics._faithfulness import faithfulness
from ragas.metrics._answer_relevance import answer_relevancy
from ragas.metrics._context_precision import context_precision
from ragas.metrics._context_recall import context_recall

from vector_store import get_retriever
from rag import get_rag_response

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
EVAL_CLIENT_ID  = 0           # No client-specific docs; only base_knowledge is used
RAGAS_LLM_MODEL = "gpt-4o"   # used when --local is not set
OLLAMA_BASE_URL  = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
METRICS = [faithfulness, answer_relevancy, context_precision, context_recall]


def load_dataset(path: str = "eval_dataset.json") -> list[dict]:
    with open(path) as f:
        return json.load(f)


def get_answer_and_contexts(question: str, retriever, session_id: str) -> tuple[str, list[str]]:
    """Run one QA turn; return the generated answer and raw context strings.

    Uses rag.get_rag_response() — the actual production pipeline (Option B:
    CLaRa compress -> Qwen generate, per .env's USE_CLARA_COMPRESS=true) —
    rather than the legacy chain_factory chain, which is unreachable in
    production and was silently scoring dead code.
    """
    # Retrieve contexts first (so we can pass them to RAGAS separately)
    docs = retriever.invoke(question)
    contexts = [doc.page_content for doc in docs]

    # Generate answer via the real pipeline. No patient profile for these
    # generic knowledge-recall questions (profile=None), matching the
    # dataset's lack of patient context.
    result = get_rag_response(
        question=question,
        client_id=EVAL_CLIENT_ID,
        chat_session_id=session_id,
        profile=None,
        is_patient_self=False,
    )
    answer = result.get("answer", "") if isinstance(result, dict) else str(result)

    return answer, contexts


def run_evaluation(items: list[dict], ragas_llm, metrics_to_run=None, warmup=False, timeout=180) -> dict:
    """Collect (question, answer, contexts, ground_truth) tuples and run RAGAS."""
    if metrics_to_run is None:
        metrics_to_run = METRICS
    retriever = get_retriever(client_id=str(EVAL_CLIENT_ID))

    questions, answers, all_contexts, ground_truths = [], [], [], []

    total = len(items)
    for i, item in enumerate(items, 1):
        q = item["question"]
        gt = item["ground_truth"]
        category = item.get("category", "")

        print(f"[{i}/{total}] {category} — {q[:70]}...")
        t0 = time.time()

        session_id = str(uuid.uuid4())   # Fresh session per question; no history bleed
        answer, contexts = get_answer_and_contexts(q, retriever, session_id)

        elapsed = time.time() - t0
        print(f"         contexts={len(contexts)}  answer_len={len(answer)}  ({elapsed:.1f}s)")

        questions.append(q)
        answers.append(answer)
        all_contexts.append(contexts)
        ground_truths.append(gt)

    print(f"\nRunning RAGAS on {total} samples …")

    if warmup:
        print("  Re-warming judge model after answer generation...", end=" ", flush=True)
        ragas_llm.langchain_llm.invoke("Respond with yes.")
        print("ready.")

    # Assign judge LLM to each metric (old-style metrics require direct assignment)
    for m in metrics_to_run:
        m.llm = ragas_llm

    dataset = Dataset.from_dict(
        {
            "question": questions,
            "answer": answers,
            "contexts": all_contexts,
            "ground_truth": ground_truths,
        }
    )

    result = evaluate(
        dataset,
        metrics=metrics_to_run,
        raise_exceptions=False,
        run_config=RunConfig(timeout=timeout, max_retries=2),
    )

    df = result.to_pandas()
    # Inject original questions so the report table is readable
    df["question"] = questions

    def mean_score(col: str) -> float:
        if col not in df.columns:
            return float("nan")
        vals = [v for v in df[col] if v is not None and str(v) != "nan"]
        return sum(vals) / len(vals) if vals else float("nan")

    all_metric_names = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
    return {
        "scores": {name: mean_score(name) for name in all_metric_names},
        "per_question": df.to_dict(orient="records"),
        "n_samples": total,
    }


def print_report(result: dict):
    print("\n" + "=" * 60)
    print("RAGAS EVALUATION RESULTS")
    print("=" * 60)
    scores = result["scores"]
    for metric, value in scores.items():
        import math
        if value is None or (isinstance(value, float) and math.isnan(value)):
            print(f"  {metric:<22}    N/A  (metric skipped or all failed)")
        else:
            bar = "█" * int(value * 20)
            print(f"  {metric:<22} {value:.4f}  {bar}")
    print(f"\n  Samples evaluated: {result['n_samples']}")
    print("=" * 60)

    print("\nPer-question breakdown:")
    print(f"{'#':<4} {'Faithful':>9} {'Relevancy':>10} {'Ctx Prec':>9} {'Ctx Rec':>9}  Question")
    print("-" * 90)
    for i, row in enumerate(result["per_question"], 1):
        f  = row.get("faithfulness", float("nan"))
        ar = row.get("answer_relevancy", float("nan"))
        cp = row.get("context_precision", float("nan"))
        cr = row.get("context_recall", float("nan"))
        q  = row.get("question", "")[:55]
        print(f"{i:<4} {f:>9.3f} {ar:>10.3f} {cp:>9.3f} {cr:>9.3f}  {q}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate NutriChatbot with RAGAS")
    parser.add_argument("--dataset",      default="eval_dataset.json")
    parser.add_argument("--limit",        type=int, default=None, help="Evaluate only first N questions")
    parser.add_argument("--category",     default=None, help="Filter by category name (substring match)")
    parser.add_argument("--out",          default=None, help="Save full results to JSON file")
    parser.add_argument("--local",        action="store_true", help="Use local Ollama models (no OpenAI)")
    parser.add_argument("--answer-model", default="adime-final", help="Ollama model for answer generation (default: adime-final)")
    parser.add_argument("--judge-model",  default="deepseek-coder-v2", help="Ollama model for RAGAS judging (default: deepseek-coder-v2)")
    args = parser.parse_args()

    items = load_dataset(args.dataset)

    if args.category:
        items = [x for x in items if args.category.lower() in x.get("category", "").lower()]
        print(f"Filtered to {len(items)} items matching category '{args.category}'")

    if args.limit:
        items = items[: args.limit]
        print(f"Limited to {len(items)} items")

    if not items:
        print("No items to evaluate after filtering.")
        return

    if args.local:
        from langchain_community.chat_models import ChatOllama
        print(f"Local mode — answer model: {args.answer_model} | judge: {args.judge_model}")
        print("  (answer_relevancy skipped — requires OpenAI-compatible embeddings)")
        ragas_llm = LangchainLLMWrapper(ChatOllama(
            model=args.judge_model,
            base_url=OLLAMA_BASE_URL,
            temperature=0,
            num_predict=1000,
        ))
        # Drop answer_relevancy in local mode — it requires embedding calls that
        # don't work reliably with local models
        metrics_to_run = [m for m in METRICS if m is not answer_relevancy]
        for m in metrics_to_run:
            m.llm = ragas_llm

        _local_warmup = True
    else:
        from langchain_openai import ChatOpenAI
        ragas_llm = LangchainLLMWrapper(ChatOpenAI(model=RAGAS_LLM_MODEL, temperature=0))
        metrics_to_run = METRICS
        _local_warmup = False

    eval_timeout = 600 if args.local else 180
    result = run_evaluation(items, ragas_llm, metrics_to_run, warmup=_local_warmup, timeout=eval_timeout)
    print_report(result)

    if args.out:
        with open(args.out, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nFull results saved to {args.out}")


if __name__ == "__main__":
    main()
