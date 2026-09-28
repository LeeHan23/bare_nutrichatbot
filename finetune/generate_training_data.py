"""
Generate synthetic multi-turn ADIME training conversations for LoRA fine-tuning.

Usage:
    python generate_training_data.py                   # 500 examples, --provider ollama (default, self-hosted, free)
    python generate_training_data.py --count 1000      # more examples
    python generate_training_data.py --from-db         # pull context chunks from pgvector
    python generate_training_data.py --provider anthropic --model claude-opus-4-8  # higher-quality, paid
    python generate_training_data.py --provider openai --model gpt-4o              # legacy path

    # Eval-failure-targeted mode (see docs/eval_and_roadmap.md Part C): reads
    # a test_rag.py --out results JSON, finds every FAILING contraindication
    # case, and generates --focus-weight extra conversations per distinct
    # failing (food, condition) combo that explicitly demonstrate the correct
    # clinical stance -- oversampling exactly the model's known weak spots
    # instead of uniform random sampling across the whole condition matrix.
    python generate_training_data.py --focus-results ../eval/results/rag.json --focus-weight 5

Output: data/train.jsonl + data/val.jsonl (ShareGPT format for Unsloth/TRL).
Focus-targeted records carry an extra "focus": {food, condition, expected_stance}
key for traceability.

Providers:
    ollama     (default) qwen2.5:32b via the self-hosted Mac Studio tunnel -- free, no API key.
    anthropic  claude-opus-4-8 by default -- pip install anthropic, needs ANTHROPIC_API_KEY.
    openai     legacy path, needs OPENAI_API_KEY and pip install openai.

Cost estimate (500 examples):
    ollama         $0 (self-hosted)
    claude-haiku-4-5   ≈ $2-4
    claude-sonnet-5    ≈ $8-15
    claude-opus-4-8    ≈ $25-40
    gpt-4-turbo    ≈ $30-40
    gpt-4o         ≈ $8-12
    gpt-4o-mini    ≈ $0.50
"""
import os
import re
import sys
import json
import random
import time
import argparse
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the system template from the app so training matches inference exactly
from chain_factory import get_system_template

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

# --- Disease conditions to cover ---
CONDITIONS = [
    "Type 2 Diabetes",
    "Hypertension",
    "Dyslipidaemia",
    "Obesity",
    "Coronary Artery Disease",
    "Heart Failure",
    "general health and wellness",
    "Type 2 Diabetes and Hypertension",
    "Dyslipidaemia and Obesity",
]

# --- Representative Malaysian patient personas ---
PERSONAS = [
    "45-year-old Malay male office worker, eats Nasi Lemak and Teh Tarik daily, sedentary lifestyle",
    "55-year-old Chinese female retiree, loves dim sum on weekends, drinks herbal soup regularly",
    "38-year-old Indian male engineer, Roti Canai for breakfast most days, high-stress job",
    "62-year-old Malay female homemaker, cooks for a large family using lots of santan and frying",
    "29-year-old Chinese male, frequent mamak stall visitor late at night, irregular meal times",
    "50-year-old Indian female with a busy work schedule, often skips lunch, loves Nasi Kandar",
    "42-year-old Malay male, exercises 2x per week but struggles with evening snacking",
    "35-year-old Chinese female vegetarian, struggles with protein intake, eats tofu and eggs daily",
    "48-year-old Indian male, retired, loves mutton curry and ghee roti on weekends",
    "31-year-old Malay female, young mother, eats communal family meals, shares dishes",
    "67-year-old Chinese male, recently diagnosed, doesn't cook — eats hawker food every meal",
    "44-year-old Indian female, moderate cook, uses a lot of spices and full-fat coconut milk",
]

# --- Clinical knowledge samples (fallback if --from-db not used) ---
CONTEXT_SAMPLES = [
    """The Malaysian Dietary Guidelines 2020 recommend the 'Suku-Suku Separuh' (Quarter-Quarter-Half) plate method:
    - 1/4 plate: complex carbohydrates (rice, bread, noodles) — prefer wholegrain options
    - 1/4 plate: protein (fish, chicken, eggs, legumes) — lean sources preferred
    - 1/2 plate: vegetables and fruits
    For diabetic patients, consistent carbohydrate distribution across meals helps with glycaemic control.
    Avoid high-GI foods: white rice in large quantities, white bread, sugary drinks (Teh Tarik, Milo).""",

    """Management of Type 2 Diabetes — dietary principles:
    Aim for 45–60g of carbohydrate per main meal. Choose lower-glycaemic index foods: basmati rice over white rice,
    sweet potato over white potato, whole-fruit over juice. Limit added sugars to <10% total energy.
    Fibre intake of 25–38g/day slows glucose absorption. Regular meal timing prevents hypoglycaemia.
    Malaysian culturally-appropriate high-fibre choices: ulam (raw herbs), kangkung, long beans, bitter gourd (peria).""",

    """Hypertension dietary management — DASH diet principles adapted for Malaysia:
    Sodium target: <2300mg/day (ideally <1500mg). Major Malaysian sodium sources: soy sauce (1 tsp = 900mg),
    belacan, processed foods, MSG. Recommend: season with turmeric, cumin, chilli (capsaicin) instead of salt.
    Potassium-rich foods for blood pressure: banana, papaya, sweet potato, spinach, tomato.
    Avoid: instant noodles (Maggi), preserved vegetables (acar), salted fish (ikan masin).""",

    """Dyslipidaemia dietary management:
    Reduce saturated fat: limit coconut milk (santan), palm oil in cooking, fatty cuts of meat.
    Replace with unsaturated fats: olive oil, canola oil for cooking.
    Omega-3 fatty acids are cardioprotective: recommend ikan kembung (Indian mackerel), ikan sardin, ikan tenggiri 3x/week.
    Soluble fibre reduces LDL: oats, psyllium husk, legumes (dhal, chickpeas).
    Plant sterols: soy products (tofu, tempeh) provide phytosterols that block cholesterol absorption.""",

    """Weight management principles:
    A deficit of 500–750 kcal/day achieves 0.5–0.75 kg/week loss — realistic and sustainable.
    Practical portion tools for Malaysian patients: a cupped palm for rice (~150g cooked), palm of hand for protein.
    Communal eating strategy: serve own plate first, fill with vegetables before scooping shared dishes.
    Liquid calories are a major source: a single Teh Tarik = 150–250 kcal. Recommend cutting sugar in drinks gradually.
    Satiety: protein and fibre increase fullness. Starting meals with soup or salad reduces total intake.""",

    """Heart failure dietary management:
    Sodium restriction: <2g sodium/day (equivalent to <5g salt). Hidden sodium in sauces, stocks, processed meats.
    Fluid restriction: typically 1.5–2L/day including water, soups, drinks, and ice.
    Daily weight monitoring: gain of >1kg overnight or >2kg in 3 days = fluid retention → contact doctor.
    Potassium monitoring required if on ACE inhibitors/ARBs: avoid high-K foods (banana, durian, potatoes).
    Small frequent meals (5–6x/day) reduce cardiac workload and dyspnoea during eating.""",

    """Chronic Kidney Disease dietary management (non-dialysis):
    Protein restriction: 0.6–0.8g/kg/day to slow progression. Choose high-biological-value protein (egg whites, fish).
    Phosphorus restriction: limit dairy, nuts, seeds, cola drinks, processed foods with phosphate additives.
    Potassium restriction if hyperkalaemic: limit banana, durian, tomato, potatoes, spinach.
    Soaking vegetables (30 min) and discarding water reduces potassium by 30–50%.
    Fluid restriction varies by urine output — assess individually.""",

    """Cardiovascular Disease prevention — Malaysian context:
    Primary prevention: achieve healthy BMI (18.5–22.9 for Asians), waist <90cm (M) / <80cm (F).
    Mediterranean dietary pattern is evidence-based: olive oil, fish, legumes, vegetables, moderate whole grains.
    Malaysian adaptation: replace santan with low-fat coconut milk (in moderation), grill/steam instead of deep-fry,
    use canola oil instead of palm oil, increase fish from local waters.
    Smoking, sedentary behaviour, and stress are key modifiable CVD risk factors alongside diet.""",
]

# --- Meta-prompt for GPT-4 to generate conversations ---
META_PROMPT = """\
You are a dataset curator creating training data for a Malaysian nutrition chatbot powered by an AI dietitian.

Generate a realistic, multi-turn conversation between a PATIENT and an AI DIETITIAN ASSISTANT.

**Patient profile:** {persona}
**Primary health condition:** {condition}
**Reference knowledge the dietitian draws from:**
{context}

**The AI dietitian MUST:**
1. Follow ADIME (Assessment → Diagnosis → Intervention → Monitoring/Evaluation), weaving each phase naturally
2. Ask open-ended questions ONLY — never yes/no questions
   - BAD: "Do you eat breakfast?"
   - GOOD: "What does a typical morning look like for you in terms of food or drinks?"
3. Build on what the patient has already said — never repeat a question already answered
4. Use warm, empathetic language: "That's a great observation," "Let's explore that together," "What if we try..."
5. Reference Malaysian foods naturally: Nasi Lemak, Roti Canai, Teh Tarik, Rendang, mamak culture, santan
6. Apply suku-suku-separuh (quarter-quarter-half plate) when explaining portions
7. Relate every piece of advice back to the patient's specific condition ('{condition}')
8. Progress the conversation — don't stay stuck in Assessment forever

**Conversation structure:**
- 6–10 TOTAL exchanges (3–5 user turns + 3–5 assistant turns alternating)
- The patient's first message should be a realistic opening concern or question
- The conversation should reach the Intervention or Monitoring phase by the end
- Feel NATURAL and PROGRESSIVE — not scripted or repetitive

**Return ONLY a valid JSON array** (no markdown, no explanation) in this exact format:
[
  {{"role": "user", "content": "..."}},
  {{"role": "assistant", "content": "..."}},
  {{"role": "user", "content": "..."}},
  {{"role": "assistant", "content": "..."}}
]"""

# --- Eval-failure focus mode (docs/eval_and_roadmap.md Part C) ---
# Appended to META_PROMPT when generating a conversation targeted at a
# specific failing contraindication combo, so the synthetic data explicitly
# demonstrates the correct clinical stance instead of leaving it to chance.
FOCUS_STANCE_INSTRUCTIONS = {
    "restrict": (
        "The dietitian's advice MUST clearly tell the patient to AVOID or "
        "STRICTLY LIMIT {food}, because of {condition}. Do not soften this "
        "into 'fine in moderation' or 'occasional treat' framing — that is "
        "the exact mistake this training example exists to correct."
    ),
    "moderate": (
        "The dietitian's advice MUST clearly frame {food} as okay only in "
        "small amounts, occasionally, or with monitoring, given {condition} "
        "— neither an outright restriction nor an unconditional yes."
    ),
    "permit": (
        "The dietitian's advice MUST clearly reassure the patient that "
        "{food} is fine given {condition}, and must NOT incorrectly "
        "restrict or discourage it."
    ),
}

FOCUS_ADDENDUM = """

**MANDATORY FOCUS REQUIREMENT — this conversation exists specifically to correct a known model error:**
At some point in the conversation, the patient MUST ask about eating or drinking {food}.
{stance_instruction}"""

# Myth-handling failures (eval/test_rag.py's `myth_check`) have no food/condition/
# stance triple to target -- they fail because the model hedges around a false
# belief instead of refuting it (or, worse, invents a reason like a fictional
# allergy for it). Same oversampling mechanism, different addendum shape.
MYTH_FOCUS_ADDENDUM = """

**MANDATORY FOCUS REQUIREMENT — this conversation exists specifically to correct a known model error:**
At some point in the conversation, the patient MUST state this belief as if it's already fact or their
established routine, not as a question: "{claim}"
The dietitian's reply MUST explicitly and plainly say this belief is inaccurate or unsupported — do NOT
just give safe advice around it while leaving the belief unaddressed; staying silent on it reads as
agreeing with it. Never attribute any food avoidance to an allergy, diagnosis, or care-team note that
hasn't already been established earlier in the conversation.{escalate_clause}"""

MYTH_ESCALATE_CLAUSE = (
    " The reply MUST also explicitly tell the patient to raise this with their doctor or care team "
    "before making any related changes."
)

_DESC_PREFIX_RE = re.compile(r"^MYTH\s+T\d+(?:\s+\S+)*:\s*")


def _condition_from_desc(desc: str) -> str:
    """Best-effort condition/context label parsed from a myth case's human-
    readable `desc` (e.g. 'MYTH T2: L3 Post-CABG+CKD4 — pantang...' ->
    'L3 Post-CABG+CKD4'), for use as the persona's condition string when
    there's no contraindication_check to source one from."""
    desc = _DESC_PREFIX_RE.sub("", desc)
    return desc.split(" — ")[0].strip() or "a relevant cardiac condition"


def _target_stance(acceptable_stances: list) -> str:
    """Pick the most clinically conservative acceptable stance to target —
    restrict > moderate > permit — so focus-generated training data always
    teaches the strongest correct behavior rather than the most lenient one."""
    lowered = [s.lower() for s in (acceptable_stances or [])]
    for stance in ("restrict", "moderate", "permit"):
        if stance in lowered:
            return stance
    return lowered[0] if lowered else "restrict"


def load_focus_combos(results_path: str) -> list[dict]:
    """Read a test_rag.py --out results JSON and extract distinct FAILING
    combos to oversample: contraindication combos {type: "contraindication",
    food, condition, expected_stance}, and myth-handling combos
    {type: "myth", claim, condition, must_escalate}.

    Only cases with passed=False are considered — the point is to generate
    more training data for exactly what the current model gets wrong, not to
    re-cover cases it already handles correctly. A case can contribute both
    kinds of combo (e.g. a myth case that also has a contraindication_check)
    since they target different failure surfaces.
    """
    with open(results_path) as f:
        data = json.load(f)

    seen = set()
    combos = []
    for case in data.get("cases", []):
        if case.get("passed"):
            continue

        check = case.get("contraindication_check")
        if check:
            food = check["food"]
            condition = check["condition"]
            stance = _target_stance(check.get("acceptable_stances", ["restrict"]))
            key = ("contraindication", food, condition, stance)
            if key not in seen:
                seen.add(key)
                combos.append({
                    "type": "contraindication",
                    "food": food,
                    "condition": condition,
                    "expected_stance": stance,
                })

        myth = case.get("myth_check")
        if myth:
            claim = myth["claim"]
            key = ("myth", claim)
            if key not in seen:
                seen.add(key)
                combos.append({
                    "type": "myth",
                    "claim": claim,
                    "condition": _condition_from_desc(case.get("desc", "")),
                    "must_escalate": bool(myth.get("must_escalate", False)),
                })
    return combos


def get_db_contexts(n_samples: int = 5) -> list[str]:
    """Pull random document chunks from pgvector as context samples."""
    try:
        from embeddings import get_embedding_function
        from langchain_community.vectorstores import PGVector
        import os

        connection_string = os.environ.get(
            "PGVECTOR_URL",
            os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nutribot"),
        )
        if connection_string.startswith("postgresql://"):
            connection_string = connection_string.replace("postgresql://", "postgresql+psycopg2://", 1)

        embedding_fn = get_embedding_function()
        # Use random nutrition queries to pull diverse chunks
        queries = [
            "diabetes diet recommendations Malaysia",
            "hypertension sodium restriction",
            "dyslipidaemia saturated fat cholesterol",
            "weight management calorie deficit",
            "heart failure fluid restriction",
            "Malaysian food portion size",
            "suku-suku-separuh plate method",
        ]
        random.shuffle(queries)
        db = PGVector(
            connection_string=connection_string,
            embedding_function=embedding_fn,
            collection_name="base_knowledge",
            use_jsonb=True,
        )
        contexts = []
        for q in queries[:n_samples]:
            docs = db.similarity_search(q, k=2)
            for d in docs:
                if d.page_content.strip() and d.page_content not in contexts:
                    contexts.append(d.page_content.strip())
        print(f"[DB] Pulled {len(contexts)} context chunks from pgvector.")
        return contexts
    except Exception as e:
        print(f"[DB] Could not connect to pgvector ({e}). Using built-in context samples.")
        return []


def _openai_generate(prompt: str, model: str, max_tokens: int) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.85,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def _ollama_generate(prompt: str, model: str, max_tokens: int) -> str:
    import requests
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.85, "num_predict": max_tokens},
        },
        # Cloudflare blocks the default requests/urllib User-Agent when hitting
        # the tunneled Ollama endpoint from off-network -- see eval/live_pipeline_smoke_test.py.
        headers={"User-Agent": "curl/8.7.1"},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


def _anthropic_generate(prompt: str, model: str, max_tokens: int) -> str:
    import anthropic
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return next((b.text for b in response.content if b.type == "text"), "").strip()


def _generate_completion(prompt: str, model: str, provider: str, max_tokens: int = 2500) -> str:
    if provider == "openai":
        return _openai_generate(prompt, model, max_tokens)
    elif provider == "ollama":
        return _ollama_generate(prompt, model, max_tokens)
    elif provider == "anthropic":
        return _anthropic_generate(prompt, model, max_tokens)
    raise ValueError(f"Unknown provider: {provider}")


def generate_conversation(
    persona: str,
    condition: str,
    context: str,
    model: str,
    attempt: int = 0,
    focus: dict | None = None,
    provider: str = "ollama",
) -> list[dict] | None:
    prompt = META_PROMPT.format(persona=persona, condition=condition, context=context)
    if focus and focus.get("type") == "myth":
        escalate_clause = MYTH_ESCALATE_CLAUSE if focus.get("must_escalate") else ""
        prompt += MYTH_FOCUS_ADDENDUM.format(claim=focus["claim"], escalate_clause=escalate_clause)
    elif focus:
        stance_instruction = FOCUS_STANCE_INSTRUCTIONS[focus["expected_stance"]].format(
            food=focus["food"], condition=focus["condition"]
        )
        prompt += FOCUS_ADDENDUM.format(food=focus["food"], stance_instruction=stance_instruction)
    try:
        text = _generate_completion(prompt, model, provider, max_tokens=2500)
        # Strip markdown code fences if the model wraps them
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])  # drop first (```json) and last (```) lines
        messages = json.loads(text)
        # Basic validation
        if not isinstance(messages, list) or len(messages) < 4:
            raise ValueError(f"Too short or invalid format: {len(messages)} turns")
        return messages
    except Exception as e:
        if attempt < 2:
            print(f"    Retry {attempt + 1}/2 after: {e}")
            time.sleep(3)
            return generate_conversation(persona, condition, context, model, attempt + 1, focus=focus, provider=provider)
        print(f"    Gave up after 3 attempts: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Generate ADIME training data for LoRA fine-tuning")
    parser.add_argument("--count", type=int, default=500, help="Uniform (non-focus) examples to generate (default: 500)")
    parser.add_argument("--provider", choices=["ollama", "anthropic", "openai"], default="ollama",
                        help="Generation backend (default: ollama -- self-hosted qwen2.5:32b, no API key needed)")
    parser.add_argument("--model", default=None,
                        help="Model for generation (default depends on --provider: "
                             "ollama -> $OLLAMA_MODEL, anthropic -> claude-opus-4-8, openai -> gpt-4o)")
    parser.add_argument("--from-db", action="store_true", help="Pull context chunks from pgvector instead of built-in samples")
    parser.add_argument("--val-split", type=float, default=0.1, help="Validation split fraction (default: 0.1)")
    parser.add_argument("--output-dir", default="data", help="Output directory (default: data/)")
    parser.add_argument("--focus-results", default=None,
                        help="Path to a test_rag.py --out results JSON; oversamples synthetic "
                             "conversations for its failing contraindication combos, in addition "
                             "to the --count uniform examples (see docs/eval_and_roadmap.md Part C)")
    parser.add_argument("--focus-weight", type=int, default=5,
                        help="Conversations to generate per distinct failing combo (default: 5)")
    args = parser.parse_args()

    if args.model is None:
        args.model = {
            "ollama": OLLAMA_MODEL,
            "anthropic": "claude-opus-4-8",
            "openai": "gpt-4o",
        }[args.provider]

    if args.provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        raise EnvironmentError("--provider anthropic requires ANTHROPIC_API_KEY in .env")
    if args.provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        raise EnvironmentError("--provider openai requires OPENAI_API_KEY in .env")

    os.makedirs(args.output_dir, exist_ok=True)

    # --- Load contexts ---
    if args.from_db:
        contexts = get_db_contexts(n_samples=30)
        if not contexts:
            print("[Warning] Falling back to built-in context samples.")
            contexts = CONTEXT_SAMPLES
    else:
        contexts = CONTEXT_SAMPLES

    # --- Load focus combos, if requested ---
    focus_combos = []
    if args.focus_results:
        focus_combos = load_focus_combos(args.focus_results)

    print(f"\nConfig:")
    print(f"  Provider:   {args.provider}")
    print(f"  Model:      {args.model}")
    print(f"  Uniform:    {args.count}")
    if args.focus_results:
        print(f"  Focus:      {len(focus_combos)} failing combo(s) x {args.focus_weight} = {len(focus_combos) * args.focus_weight} extra examples (from {args.focus_results})")
    print(f"  Val split:  {args.val_split:.0%}")
    print(f"  Contexts:   {len(contexts)}")
    print(f"  Output dir: {args.output_dir}/\n")

    # --- Build job list: focus-targeted jobs first, then the uniform matrix ---
    # Each job is (persona, condition, context, focus_or_None).
    jobs = []
    for combo in focus_combos:
        for _ in range(args.focus_weight):
            jobs.append((random.choice(PERSONAS), combo["condition"], random.choice(contexts), combo))

    uniform_combos = [(p, c, ctx) for p in PERSONAS for c in CONDITIONS for ctx in contexts]
    random.shuffle(uniform_combos)
    while len(uniform_combos) < args.count:
        extra = uniform_combos.copy()
        random.shuffle(extra)
        uniform_combos.extend(extra)
    for persona, condition, context in uniform_combos[: args.count]:
        jobs.append((persona, condition, context, None))

    random.shuffle(jobs)
    total = len(jobs)

    # --- Generate ---
    train_path = os.path.join(args.output_dir, "train.jsonl")
    val_path = os.path.join(args.output_dir, "val.jsonl")
    val_cutoff = int(total * (1 - args.val_split))

    written_train = written_val = failed = focus_written = 0
    with open(train_path, "w") as f_train, open(val_path, "w") as f_val:
        for i, (persona, condition, context, focus) in enumerate(jobs):
            tag = " [FOCUS]" if focus else ""
            print(f"[{i+1:4d}/{total}] {condition[:35]:35s} | {persona[:40]}{tag}")

            messages = generate_conversation(persona, condition, context, args.model, focus=focus, provider=args.provider)
            if not messages:
                failed += 1
                continue

            # Build the full system prompt with context filled in (same as inference)
            system_content = get_system_template(condition).replace("{context}", context)

            record = {
                "conversations": [
                    {"role": "system", "content": system_content},
                    *messages,
                ]
            }
            if focus:
                record["focus"] = focus
                focus_written += 1
            line = json.dumps(record, ensure_ascii=False) + "\n"

            if i < val_cutoff:
                f_train.write(line)
                written_train += 1
            else:
                f_val.write(line)
                written_val += 1

            # Light rate limiting for hosted providers (Ollama has no rate limit to respect,
            # but a brief pause avoids hammering a single self-hosted model instance)
            if i % 20 == 19:
                time.sleep(1)

    print(f"\nDone.")
    print(f"  Train: {written_train:4d} examples → {train_path}")
    print(f"  Val:   {written_val:4d} examples → {val_path}")
    if args.focus_results:
        print(f"  Focus-targeted: {focus_written:4d} of {written_train + written_val} written")
    print(f"  Failed:{failed:4d}")


if __name__ == "__main__":
    main()
