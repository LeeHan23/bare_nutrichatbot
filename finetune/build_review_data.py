"""
Turn the clinicians' reviews on eval.computationalrd.com into fine-tune data.

Reads data/judge_calibration_cases.json (the answers shown on the eval site)
and data/eval_calibration_reviews.json (what reviewers submitted), and writes
an mlx_lm.lora data dir: the attempt #2 set (finetune/data_focus_v3) plus one
or more examples per reviewed case.

What counts as feedback:
  - Reviewer notes are the signal. The verdict dropdown is used
    inconsistently (e.g. myth:101 has ACCEPT/HEDGE + Agree YES on a PASS), so
    pass/fail is never derived from it.
  - Case with notes -> the bot's answer rewritten to apply every note.
  - Personalization case all reviewers marked PASS with no notes -> the
    original answer, as an "keep doing this" anchor.
  - Disputed stance case (a reviewer verdict outside the eval's
    acceptable_stances, e.g. banana for CKD3: eval says RESTRICT, both
    clinicians said PERMIT) -> trained on in NEITHER direction, and any
    data_focus_v3 example targeting the same food+condition is dropped.
    Needs a dietitian decision, then an update to eval/test_rag.py.

Scope anchors (--scope-anchors, added for v4): v3 trained on zero
non-nutrition questions and drifted into adding diet/medication advice to
general-education answers (eval 149/154/167/169). For every non-nutrition
Component, new patient questions — one batch answerable as general
education, one that must be deferred — are written from taxonomy.COMPONENT_SCOPE,
answered by the base model through the live prompt, and kept only if
eval/test_rag.judge_scope_adherence passes. Questions close to an eval case
are skipped, so the eval's scope cases stay untrained. --base none drops the
legacy ADIME set, whose "Nutrition Assistant, T2DM/HTN" system prompt is
not the production prompt. Each build writes <out>/scope_anchors.json;
--anchors <that file> reuses those anchors instead of generating new ones and
applies the clinicians' verdicts from the v4_anchors / v4_scope_fix tabs.

Stance rulings (stance_ruling tab): a dietitian's ruling replaces the earlier
stance reviews for that case. It is trained only once eval/test_rag.py's
acceptable_stances includes it, so the eval and the training target agree.

Training inputs match inference exactly: each example's user turn is the
prompt rag.get_rag_response() actually sends Ollama (captured by stubbing
call_ollama_generate), so retrieval, profile, and prompt rules are the live
ones. The question is paraphrased first, so the eval gate still tests the
verbatim eval question rather than a memorised one.

Usage (Han Server — needs Postgres + the Mac Studio's Ollama):
  .venv/bin/python finetune/build_review_data.py --dry-run     # list, no LLM calls
  .venv/bin/python finetune/build_review_data.py               # ~1 hour
  .venv/bin/python finetune/build_review_data.py --base none --out finetune/data_mlx_v4   # v4
Then read <out>/review_sheet.md before training on it.
"""
import argparse
import csv
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "eval"))

CASES_PATH = os.path.join(ROOT, "data", "judge_calibration_cases.json")
REVIEWS_PATH = os.path.join(ROOT, "data", "eval_calibration_reviews.json")
INTEGRATED_CSV = os.path.join(ROOT, "eval", "integrated_into_v3.csv")
# Eval-site tabs whose ids are scope_anchors.json ids, not eval case ids (scripts/add_v4_review_tabs.py).
ANCHOR_TABS = {"kept": "v4_anchors", "rejected": "v4_scope_fix"}

PARAPHRASE_PROMPT = """Rewrite this patient's chat message so it asks the same thing in different words.
Keep the same language (English, Bahasa Malaysia or Manglish), the same claim or food, and the same
facts about what they did. Output only the rewritten message.

Message: {question}"""

ANCHOR_QUESTIONS_PROMPT = """Write {n} different short chat messages a Malaysian heart patient might send to a
health coaching chatbot about {label}. Every message must be a question that should be {kind}.

What the chatbot may explain (general education): {in_scope}
What it must defer to the care team: {out_of_scope}

{guidance}
Vary the wording and topics. Make one of them Bahasa Malaysia. One message per line, no numbering,
nothing else."""

ANCHOR_KIND = {
    "GENERAL_EDUCATION": ("answered with general education",
                          "Ask about general facts, not about the patient's own numbers, doses or plan."),
    "DEFERRED": ("deferred to the care team",
                 "Ask for something personal from the out-of-scope list (own numbers, own target, own dose or plan)."),
}

REWRITE_PROMPT = """You are fixing a reply from a cardiac-care nutrition chatbot.

These are the exact instructions and patient context the chatbot was given:
<instructions>
{live_prompt}
</instructions>

This was its reply:
<reply>
{answer}
</reply>

Clinical reviewers (a cardiologist and a dietitian) left these corrections on that reply:
{notes}

Write the corrected reply. Apply every correction. Still follow every rule in the instructions
(language, length, follow-up question, referrals). Do not add patient facts that are not in the
instructions. Output only the reply text."""


def load_feedback(eval_cases: dict) -> tuple[dict, set]:
    """-> ({case_id: {"notes": [...], "anchor": bool}}, disputed {(food, condition)}).

    Case facts come from eval/test_rag.py, not the eval-site file: some reviews
    (myth:103/105/106, stance:16/24/25) are for answers no longer on the site.
    Disputed case ids are left out of the first dict. "rule:" sign-offs are
    myheart_db.py rules, not chat answers, so they are skipped."""
    with open(REVIEWS_PATH, encoding="utf-8") as f:
        reviews = json.load(f)

    feedback, disputed, disputed_ids = {}, set(), set()
    rulings = {int(k.split(":")[1]): [r for r in rv if r.get("verdict")]
               for k, rv in reviews.items() if k.startswith("stance_ruling:")}
    for key, rv in reviews.items():
        judge_key, cid = key.split(":")
        rv = [r for r in rv if r.get("verdict")]
        if judge_key in {"rule", "stance_ruling", *ANCHOR_TABS.values()} or not rv:
            continue
        cid = int(cid)
        check = eval_cases[cid].get("contraindication_check")
        if judge_key == "stance" and check:
            if rulings.get(cid):
                continue  # the dietitian's ruling replaces these
            if any(r["verdict"].lower() not in check["acceptable_stances"] for r in rv):
                disputed.add((check["food"], check["condition"]))
                disputed_ids.add(cid)
                continue
        entry = feedback.setdefault(cid, {"notes": [], "anchor": False})
        entry["notes"] += [f"[{r['reviewer']}] {r['notes'].strip()}" for r in rv if r.get("notes", "").strip()]
        if judge_key == "personalization" and all(r["verdict"] == "PASS" for r in rv):
            entry["anchor"] = True
    for cid, rv in rulings.items():
        if not rv:
            continue
        check = eval_cases[cid]["contraindication_check"]
        stances = {r["verdict"].lower() for r in rv}
        if len(stances) > 1 or not stances <= set(check["acceptable_stances"]):
            print(f"Stance ruling {sorted(stances)} for case {cid} ({check['food']} / {check['condition']}) "
                  f"doesn't match eval/test_rag.py {check['acceptable_stances']}: not trained until they agree")
            disputed.add((check["food"], check["condition"]))
            disputed_ids.add(cid)
            continue
        entry = feedback.setdefault(cid, {"notes": [], "anchor": False})
        entry["notes"].append(f"[dietitian ruling] The correct stance for this patient is {stances.pop().upper()}.")
        entry["notes"] += [f"[{r['reviewer']}] {r['notes'].strip()}" for r in rv if r.get("notes", "").strip()]
    for cid in disputed_ids:
        feedback.pop(cid, None)
    return feedback, disputed


def answers_by_case() -> dict:
    # Cases already trained into v3 were removed from the site; their reviewed answers live in the CSV.
    with open(INTEGRATED_CSV, encoding="utf-8", newline="") as f:
        answers = {int(r["case_id"]): r["bot_answer"] for r in csv.DictReader(f)}
    with open(CASES_PATH, encoding="utf-8") as f:
        judges = json.load(f)["judges"]
    answers.update({c["id"]: c["answer"] for k, j in judges.items() if k not in {"v3_review", *ANCHOR_TABS.values()} for c in j["cases"]})
    return answers


def base_records(base_dir: str, disputed: set) -> tuple[list, list, int]:
    """data_focus_v3 (ShareGPT `conversations`) -> mlx `messages`, minus disputed focus targets."""
    out, dropped = {"train": [], "val": []}, 0
    if base_dir == "none":
        return [], [], 0
    for split in out:
        with open(os.path.join(base_dir, f"{split}.jsonl"), encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                focus = rec.get("focus") or {}
                if (focus.get("food"), focus.get("condition")) in disputed:
                    dropped += 1
                    continue
                msgs = rec["conversations"]
                # --mask-prompt trains on the final message only, so it must be the assistant's.
                while msgs[-1]["role"] != "assistant":
                    msgs = msgs[:-1]
                out[split].append({"messages": msgs})
    return out["train"], out["val"], dropped


def capture_live_prompt(case: dict, question: str) -> str:
    """Run the real pipeline for `question` with generation stubbed out, return the Qwen prompt."""
    import rag
    from database import SessionLocal, add_chat_message, clear_chat_history
    from test_rag import load_profile

    captured = []
    real_generate = rag.call_ollama_generate
    rag.call_ollama_generate = lambda prompt, *a, **k: captured.append(prompt) or "(captured)"
    # "keepalive" skips history load + persist; scripted prior turns need a real session.
    session_id = f"review-data-{case['id']}" if case.get("prior_turns") else "keepalive"
    try:
        if case.get("prior_turns"):
            with SessionLocal() as s:
                for turn in case["prior_turns"]:
                    add_chat_message(s, session_id, case["patient_id"], turn["role"], turn["content"])
        profile = load_profile(case["patient_id"], case.get("profile_overrides"))
        rag.get_rag_response(
            question=question,
            client_id=profile.get("client_id", 4),
            chat_session_id=session_id,
            profile=profile,
            is_patient_self=case.get("is_patient_self", False),
        )
    finally:
        rag.call_ollama_generate = real_generate
        if case.get("prior_turns"):
            with SessionLocal() as s:
                clear_chat_history(s, session_id)
    if not captured:
        raise RuntimeError(f"case {case['id']}: pipeline returned before generation (no prompt captured)")
    return captured[0]


def scope_anchors(n: int, model: str, provider: str) -> list[dict]:
    """-> [{"component", "expected", "patient_id", "question", "prompt", "answer"}] that pass the scope judge."""
    import difflib
    import rag
    import taxonomy
    from generate_training_data import _generate_completion
    from test_rag import CASES, judge_scope_adherence, load_profile
    from vector_store import detect_query_component

    eval_questions = [c["question"].lower() for c in CASES if c.get("question")]
    patients = sorted({c["patient_id"] for c in CASES})
    out, turn = [], 0
    for component, scope in taxonomy.COMPONENT_SCOPE.items():
        if component == "nutrition":
            continue
        for expected, (kind, guidance) in ANCHOR_KIND.items():
            raw = _generate_completion(ANCHOR_QUESTIONS_PROMPT.format(
                n=n + 2, label=taxonomy.COMPONENT_LABELS.get(component, component), kind=kind,
                guidance=guidance, **scope), model, provider, 400)
            kept = 0
            for q in (line.strip(" -*\t\"") for line in raw.splitlines()):
                if kept == n or not q:
                    continue
                if any(difflib.SequenceMatcher(None, q.lower(), e).ratio() > 0.75 for e in eval_questions):
                    print(f"  skip (close to an eval case): {q}")
                    continue
                routed = detect_query_component(q)
                if routed in (None, "nutrition"):
                    # The Component Scope block only reaches the prompt when routing fires.
                    print(f"  skip (routes to {routed!r}, asked for {component!r}): {q}")
                    continue
                # Judge against the component live chat would use, not the one asked for:
                # "what do my cholesterol levels mean" was asked for foundations, routes to lipid.
                pid = patients[turn % len(patients)]
                turn += 1
                case = {"id": f"anchor-{routed}", "patient_id": pid, "is_patient_self": True}
                prompt = capture_live_prompt(case, q)
                conditions = str(load_profile(pid, None).get("condition") or "")
                for _ in range(2):
                    answer = rag.call_ollama_generate(prompt)
                    ok, reason = judge_scope_adherence(answer, q, routed, expected, conditions)
                    if ok:
                        out.append({"component": routed, "expected": expected, "patient_id": pid,
                                    "question": q, "prompt": prompt, "answer": answer})
                        kept += 1
                        print(f"  anchor {routed}/{expected} P{pid}: {q}", flush=True)
                        break
                    print(f"  judge rejected ({reason[:100]}): {q}")
    return out


def reviewed_anchors(path: str, model: str, provider: str) -> list[dict]:
    """scope_anchors.json + the clinicians' verdicts -> anchors to train on.
    Any NEEDS FIX: rewritten from the notes, or dropped if there are none.
    Judge-rejected anchors are used only once a clinician has reviewed them."""
    from generate_training_data import _generate_completion
    with open(path, encoding="utf-8") as f:
        anchors = json.load(f)
    with open(REVIEWS_PATH, encoding="utf-8") as f:
        reviews = json.load(f)
    out = []
    for a in anchors:
        tab = ANCHOR_TABS.get(a["status"])
        if not tab:
            continue
        rv = [r for r in reviews.get(f"{tab}:{a['id']}", []) if r.get("verdict")]
        if any(r["verdict"] == "NEEDS FIX" for r in rv):
            notes = [f"[{r['reviewer']}] {r['notes'].strip()}" for r in rv if r.get("notes", "").strip()]
            if not notes:
                continue
            a = {**a, "notes": notes, "original": a["answer"], "answer": _generate_completion(
                REWRITE_PROMPT.format(live_prompt=a["prompt"], answer=a["answer"], notes="\n".join(notes)),
                model, provider, 800)}
        elif not rv and a["status"] == "rejected":
            continue
        out.append(a)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", default=os.path.join(ROOT, "finetune", "data_focus_v3"),
                   help='legacy ADIME set to include, or "none"')
    p.add_argument("--out", default=os.path.join(ROOT, "finetune", "data_mlx_v3"))
    p.add_argument("--variants", type=int, default=2, help="paraphrased examples per reviewed case (default 2)")
    p.add_argument("--scope-anchors", type=int, default=0,
                   help="judge-checked anchors per non-nutrition component and kind (v4 used 3)")
    p.add_argument("--anchors", default=None,
                   help="reuse a scope_anchors.json (with clinician verdicts) instead of generating anchors")
    p.add_argument("--provider", choices=["ollama", "anthropic", "openai"], default="ollama")
    p.add_argument("--model", default=None, help="rewrite/paraphrase model (default: $OLLAMA_MODEL)")
    p.add_argument("--dry-run", action="store_true", help="list what would be built, no LLM calls")
    args = p.parse_args()

    from test_rag import CASES
    eval_cases = {c["id"]: c for c in CASES}
    feedback, disputed = load_feedback(eval_cases)
    train, val, dropped = base_records(args.base, disputed)
    print(f"Disputed stance combos (excluded both ways, need a dietitian decision): {sorted(disputed)}")
    print(f"Base {args.base}: {len(train)} train + {len(val)} val kept, {dropped} disputed focus examples dropped")
    for cid, fb in sorted(feedback.items()):
        kind = "rewrite" if fb["notes"] else "anchor" if fb["anchor"] else "skip (no notes)"
        print(f"  case {cid:>3}: {kind}" + "".join(f"\n      {n}" for n in fb["notes"]))
    if args.dry_run:
        return

    from llm import OLLAMA_MODEL
    from generate_training_data import _generate_completion
    import rag
    model = args.model or OLLAMA_MODEL
    answers = answers_by_case()

    review, sheet = [], ["# Review-derived training examples\n",
                         "Check every rewritten reply before training. Disputed (not trained): "
                         + ", ".join(f"{f} / {c}" for f, c in sorted(disputed)) + "\n"]
    for cid, fb in sorted(feedback.items()):
        if not (fb["notes"] or fb["anchor"]):
            continue
        case = eval_cases[cid]
        for v in range(args.variants):
            question = _generate_completion(PARAPHRASE_PROMPT.format(question=case["question"]), model, args.provider, 200)
            live_prompt = capture_live_prompt(case, question)
            if cid not in answers:
                # Reviewed answer no longer on the eval site: apply the notes to a fresh one.
                answers[cid] = rag.call_ollama_generate(capture_live_prompt(case, case["question"]))
            if fb["notes"]:
                target = _generate_completion(
                    REWRITE_PROMPT.format(live_prompt=live_prompt, answer=answers[cid], notes="\n".join(fb["notes"])),
                    model, args.provider, 800)
            else:
                target = answers[cid]
            review.append({"messages": [{"role": "user", "content": live_prompt},
                                        {"role": "assistant", "content": target}]})
            sheet.append(f"\n## Case {cid} variant {v + 1}\n\n**Question:** {question}\n\n"
                         + (f"**Notes:**\n" + "\n".join(f"- {n}" for n in fb["notes"]) + "\n\n"
                            f"**Original reply:**\n\n{answers[cid]}\n\n" if fb["notes"] else "*(approved as-is)*\n\n")
                         + f"**Training target:**\n\n{target}\n")
            print(f"  case {cid} v{v + 1} done", flush=True)

    anchors = []
    if args.anchors:
        anchors = reviewed_anchors(args.anchors, model, args.provider)
    elif args.scope_anchors:
        anchors = [{"id": 1001 + i, "status": "kept", "judge_reason": "", **a}
                   for i, a in enumerate(scope_anchors(args.scope_anchors, model, args.provider))]
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "scope_anchors.json"), "w", encoding="utf-8") as f:
            json.dump(anchors, f, indent=1, ensure_ascii=False)
    if anchors:
        sheet.append("\n# Scope anchors (base-model answers that passed the scope judge or a clinician)\n")
        for i, a in enumerate(anchors):
            row = {"messages": [{"role": "user", "content": a["prompt"]},
                                {"role": "assistant", "content": a["answer"]}]}
            # Every 10th anchor validates, so --base none still has a valid split.
            (val if i % 10 == 9 else review).append(row)
            sheet.append(f"\n## {a['component']} / {a['expected']} (P{a['patient_id']}, #{a['id']})\n\n"
                         f"**Question:** {a['question']}\n\n"
                         + (f"**Notes:**\n" + "\n".join(f"- {n}" for n in a["notes"])
                            + f"\n\n**Original reply:**\n\n{a['original']}\n\n" if a.get("notes") else "")
                         + f"**Training target:**\n\n{a['answer']}\n")
        print(f"Scope anchors: {len(anchors)} kept")

    train += review
    random.Random(0).shuffle(train)
    os.makedirs(args.out, exist_ok=True)
    for name, rows in (("train.jsonl", train), ("valid.jsonl", val)):
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    with open(os.path.join(args.out, "review_sheet.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(sheet))
    with open(os.path.join(args.out, "trained_case_ids.json"), "w") as f:
        json.dump(sorted({cid for cid, fb in feedback.items() if fb["notes"] or fb["anchor"]}), f)
    print(f"\nWrote {len(train)} train ({len(review)} from reviews) + {len(val)} valid -> {args.out}")
    print(f"Read {args.out}/review_sheet.md before training.")


if __name__ == "__main__":
    main()
