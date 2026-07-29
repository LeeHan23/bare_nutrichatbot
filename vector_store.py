import os
import json
import time
from typing import List, Set

from dotenv import load_dotenv
from pydantic import Field
from langchain_community.vectorstores import PGVector
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun

from embeddings import get_embedding_function

load_dotenv()

PGVECTOR_URL = os.environ.get(
    "PGVECTOR_URL",
    os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/nutribot",
    ),
)

# Persisted retrieval-quality signal — the [TopicBoost] print line below was
# previously the only record of retrieval behavior (stdout/journald only, no
# way to analyze it later). This appends one JSON line per query instead,
# so "is retrieval the bottleneck on this failure" can eventually be answered
# from data instead of re-reading logs by hand (see docs/eval_and_roadmap.md
# Part C #4 / Part D). Path is computed from this file's location, not cwd —
# relative paths here have bitten cron jobs before in this project.
RETRIEVAL_LOG_PATH = os.getenv(
    "RETRIEVAL_LOG_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "retrieval_quality.jsonl"),
)


def _log_retrieval_quality(record: dict) -> None:
    """Best-effort JSONL append. Never let logging break retrieval itself."""
    try:
        os.makedirs(os.path.dirname(RETRIEVAL_LOG_PATH), exist_ok=True)
        with open(RETRIEVAL_LOG_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        print(f"[TopicBoost] retrieval-quality log write failed: {e}")


# ────────────────────────────────────────────────────────────────────────
# TOPIC TAXONOMY
# ────────────────────────────────────────────────────────────────────────
# Maps a phrase that might appear in a query (or patient condition) to a
# set of doc_topics tags used in the metadata. When a phrase is found in
# the query, chunks tagged with the listed topics get a score boost.
#
# Both English and Bahasa Malaysia phrases are supported. To extend, just
# add another entry. Keep phrases lowercase.

TOPIC_HINTS = {
    # Hypertension / blood pressure
    "hypertension":            {"hypertension", "blood pressure", "hypertension management"},
    "high blood pressure":     {"hypertension", "blood pressure", "hypertension management"},
    "blood pressure":          {"hypertension", "blood pressure", "hypertension management"},
    "darah tinggi":            {"hypertension", "blood pressure", "hypertension management"},
    "tekanan darah":           {"hypertension", "blood pressure"},

    # Heart failure
    "heart failure":           {"heart failure", "HF management"},
    "congestive heart":        {"heart failure", "HF management"},
    "fluid restriction":       {"heart failure", "HF management"},
    "fluid overload":          {"heart failure", "HF management"},
    "kegagalan jantung":       {"heart failure"},

    # Cholesterol / lipids / fats
    "cholesterol":             {"cholesterol", "lipid management", "cholesterol management",
                                "dyslipidaemia", "lipid disorder"},
    "cholestrol":              {"cholesterol", "lipid management"},  # misspelling in source docs
    "lipid":                   {"lipid management", "dyslipidaemia"},
    "ldl":                     {"cholesterol", "lipid management"},
    "hdl":                     {"cholesterol", "lipid management"},
    "trans fat":               {"cholesterol management", "dyslipidaemia", "fats"},
    "saturated fat":           {"cholesterol management", "dyslipidaemia", "fats"},
    " fat ":                   {"cholesterol management", "dyslipidaemia", "fats"},
    "fats":                    {"cholesterol management", "dyslipidaemia", "fats"},
    "lemak":                   {"cholesterol management", "dyslipidaemia", "fats"},

    # Sodium / salt
    "sodium":                  {"sodium intake", "sodium reduction", "DASH diet"},
    "salt":                    {"sodium intake", "sodium reduction"},
    "garam":                   {"sodium intake", "sodium reduction"},
    "masin":                   {"sodium intake", "sodium reduction"},

    # Diabetes / blood sugar
    "diabetes":                {"diabetes", "T2DM", "diabetes management", "blood sugar"},
    "diabetic":                {"diabetes", "T2DM", "diabetes management"},
    "blood sugar":             {"blood sugar", "diabetes management", "glucose"},
    "blood glucose":           {"blood sugar", "diabetes management", "glucose"},
    "kencing manis":           {"diabetes", "T2DM", "blood sugar"},
    "gula":                    {"diabetes", "blood sugar", "sugar intake"},
    "t2dm":                    {"diabetes", "T2DM", "DSME"},

    # Coronary artery disease / cardiac events
    "cad":                     {"CAD", "coronary artery disease", "stable angina"},
    "coronary":                {"CAD", "coronary artery disease", "coronary heart disease"},
    "angina":                  {"CAD", "stable angina", "coronary artery disease"},
    "chest pain":              {"CAD", "stable angina"},
    "heart attack":            {"CAD", "coronary heart disease", "post-MI care"},
    "myocardial infarction":   {"CAD", "coronary heart disease", "post-MI care"},
    "post-mi":                 {"post-MI care", "cardiac rehabilitation"},
    "pci":                     {"PCI", "coronary intervention", "post-procedure care"},

    # Exercise / physical activity
    "exercise":                {"physical activity", "exercise", "exercise prescription",
                                "cardiac exercise", "cardiac rehabilitation"},
    "physical activity":       {"physical activity", "exercise"},
    "workout":                 {"physical activity", "exercise"},
    "senaman":                 {"physical activity", "exercise"},
    "aktiviti fizikal":        {"physical activity", "exercise"},
    "bersenam":                {"physical activity", "exercise"},

    # Cardiac rehab
    "rehab":                   {"cardiac rehabilitation"},
    "rehabilitation":          {"cardiac rehabilitation"},

    # Smoking / tobacco
    "smoking":                 {"smoking cessation", "tobacco", "tobacco use disorder"},
    "smoke":                   {"smoking cessation", "tobacco"},
    "cigarette":               {"smoking cessation", "tobacco"},
    "tobacco":                 {"smoking cessation", "tobacco"},
    "nicotine":                {"smoking cessation", "tobacco", "nicotine"},
    "merokok":                 {"smoking cessation", "tobacco", "berhenti merokok"},
    "berhenti merokok":        {"smoking cessation", "berhenti merokok"},

    # Mental health
    "depression":              {"depression", "mental health", "psychological health"},
    "anxiety":                 {"mental health", "psychological health", "anxiety"},
    "stress":                  {"psychological health", "stress", "mental health"},

    # General diet / nutrition (broad — match on common eating words)
    "diet":                    {"nutrition", "diet", "MDG", "heart-healthy diet", "healthy eating"},
    "nutrition":               {"nutrition", "diet", "MDG", "heart-healthy diet"},
    " eat ":                   {"nutrition", "diet", "heart-healthy diet", "healthy eating"},
    "makan":                   {"nutrition", "diet", "MDG", "heart-healthy diet"},
    "pemakanan":               {"nutrition", "diet", "MDG"},
    "food":                    {"nutrition", "diet", "healthy eating"},

    # Sleep
    "sleep":                   {"sleep", "healthy lifestyle"},
    "tidur":                   {"sleep", "healthy lifestyle"},

    # Sugar
    "sugar":                   {"sugar intake", "diabetes management"},

    # CVD / overall cardiovascular
    "cvd":                     {"CVD prevention", "cardiovascular health", "ASCVD prevention"},
    "cardiovascular":          {"CVD prevention", "cardiovascular health"},
    "heart disease":           {"CVD prevention", "cardiovascular health",
                                "coronary heart disease"},
    "ascvd":                   {"ASCVD prevention", "CVD prevention"},

    # Chronic kidney disease / renal nutrition
    "chronic kidney":          {"CKD", "renal nutrition", "kidney disease management"},
    "kidney disease":          {"CKD", "renal nutrition", "kidney disease management"},
    " ckd ":                   {"CKD", "renal nutrition", "kidney disease management"},
    "renal":                   {"CKD", "renal nutrition", "kidney disease management"},
    "potassium":               {"CKD", "renal nutrition", "potassium restriction"},
    "phosphorus":              {"CKD", "renal nutrition", "phosphorus restriction"},
    "fluid restriction":       {"CKD", "heart failure", "HF management"},
    "penyakit buah pinggang":  {"CKD", "renal nutrition"},
    "ginjal":                  {"CKD", "renal nutrition"},

    # PCOS / insulin resistance
    "pcos":                    {"PCOS", "insulin resistance", "hormonal health"},
    "polycystic":              {"PCOS", "insulin resistance"},
    "insulin resistance":      {"insulin resistance", "T2DM", "diabetes management"},
    "rintangan insulin":       {"PCOS", "insulin resistance"},

    # Obesity / weight
    "obesity":                 {"obesity", "weight management", "BMI"},
    "overweight":              {"obesity", "weight management"},
    "berat badan":             {"obesity", "weight management"},
    "obesiti":                 {"obesity", "weight management"},

    # Post-surgical / cardiac procedures
    "cabg":                    {"cardiac rehabilitation", "post-MI care", "CAD"},
    "post-cabg":               {"cardiac rehabilitation", "post-MI care"},
    "bypass":                  {"cardiac rehabilitation", "CAD"},
    "stent":                   {"PCI", "post-procedure care", "CAD"},
}


def detect_query_topics(query: str) -> Set[str]:
    """Match a query against TOPIC_HINTS, return the union of matched topic tags."""
    q = " " + query.lower() + " "  # padding lets us match " eat " etc.
    matched: Set[str] = set()
    for phrase, topics in TOPIC_HINTS.items():
        if phrase in q:
            matched.update(topics)
    return matched


# ────────────────────────────────────────────────────────────────────────
# RETRIEVERS
# ────────────────────────────────────────────────────────────────────────
def get_connection_string() -> str:
    url = PGVECTOR_URL
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


class MergedRetriever(BaseRetriever):
    """Combines results from multiple retrievers, deduplicating by page_content."""
    retrievers: List[BaseRetriever]

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        seen = set()
        results = []
        for retriever in self.retrievers:
            for doc in retriever.invoke(query):
                if doc.page_content not in seen:
                    seen.add(doc.page_content)
                    results.append(doc)
        return results


class TopicBoostedRetriever(BaseRetriever):
    """
    Wraps a base retriever and re-ranks results by topic overlap.

    Algorithm:
        1. Fetch candidates from the base retriever (a larger pool than top_k)
        2. Detect query topics from TOPIC_HINTS
        3. Add patient conditions as additional topic signals if provided
        4. Score each candidate:
               final_score = (1 / (rank+1))   # original ranking
                           + boost_factor × overlap_ratio
        5. Sort and return the top_k candidates

    Designed to be soft, not destructive:
      - Chunks without doc_topics still appear if embedding-similar
      - Chunks with no topic match keep their original rank
      - If query has no topic signal, returns base ranking unchanged
    """
    base_retriever: BaseRetriever
    top_k: int = 5
    boost_factor: float = 0.5
    patient_conditions: List[str] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        candidates = self.base_retriever.invoke(query)
        if not candidates:
            return []

        # Detect topics — combine query and patient condition signals
        query_topics = detect_query_topics(query)
        for cond in self.patient_conditions:
            query_topics |= detect_query_topics(cond)

        if not query_topics:
            # No topic signal → return base ranking, truncated
            _log_retrieval_quality({
                "timestamp": time.time(),
                "query": query,
                "conditions": self.patient_conditions,
                "n_candidates": len(candidates),
                "top_k": self.top_k,
                "query_topics": [],
                "boosted": False,
                "n_boosted": 0,
                "boost_ratio": None,
                "results": [
                    {"rank": rank, "doc_topics": doc.metadata.get("doc_topics", []),
                     "source": doc.metadata.get("source")}
                    for rank, doc in enumerate(candidates[: self.top_k])
                ],
            })
            return candidates[: self.top_k]

        # Score each candidate
        scored = []
        for rank, doc in enumerate(candidates):
            base_score = 1.0 / (rank + 1)
            doc_topics = set(doc.metadata.get("doc_topics", []))
            overlap_ratio = (
                len(query_topics & doc_topics) / len(query_topics)
                if query_topics
                else 0.0
            )
            final_score = base_score + self.boost_factor * overlap_ratio
            scored.append((final_score, rank, overlap_ratio, doc))

        # Sort by score descending, original rank as tiebreaker
        scored.sort(key=lambda x: (-x[0], x[1]))

        # Observability — visible in systemd logs, and persisted to
        # RETRIEVAL_LOG_PATH for later analysis (see comment above).
        top = scored[: self.top_k]
        n_boosted = sum(
            1 for _, _, _, d in top
            if set(d.metadata.get("doc_topics", [])) & query_topics
        )
        print(
            f"[TopicBoost] topics={sorted(query_topics)} | "
            f"boosted {n_boosted}/{self.top_k} | "
            f"conditions={self.patient_conditions}"
        )
        _log_retrieval_quality({
            "timestamp": time.time(),
            "query": query,
            "conditions": self.patient_conditions,
            "n_candidates": len(candidates),
            "top_k": self.top_k,
            "query_topics": sorted(query_topics),
            "boosted": True,
            "n_boosted": n_boosted,
            "boost_ratio": round(n_boosted / self.top_k, 3),
            "results": [
                {"rank": orig_rank, "final_score": round(score, 3),
                 "overlap_ratio": round(overlap, 3),
                 "doc_topics": doc.metadata.get("doc_topics", []),
                 "source": doc.metadata.get("source")}
                for score, orig_rank, overlap, doc in top
            ],
        })

        return [doc for _, _, _, doc in top]


# ────────────────────────────────────────────────────────────────────────
# PUBLIC FACTORY
# ────────────────────────────────────────────────────────────────────────
def get_retriever(
    client_id: str,
    patient_conditions: List[str] = None,
) -> BaseRetriever:
    """
    Hybrid retriever:
        base_knowledge + client_{id}_knowledge → merge & dedupe
                                              → topic-boost re-rank
                                              → return top K

    Args:
        client_id: tenant identifier for the per-client collection.
        patient_conditions: optional list of clinical conditions
            (e.g., ["Heart Failure", "Hypertension"]). When provided,
            chunks tagged with related topics are boosted further.
    """
    connection_string = get_connection_string()
    embedding_function = get_embedding_function()

    # Pull a wider candidate pool (k=15 per collection) so the re-ranker
    # has room to actually move things around. Trimmed back to top_k=5
    # in TopicBoostedRetriever.
    base_db = PGVector(
        connection_string=connection_string,
        embedding_function=embedding_function,
        collection_name="base_knowledge",
        use_jsonb=True,
    )
    base_retriever = base_db.as_retriever(search_kwargs={"k": 15})

    client_db = PGVector(
        connection_string=connection_string,
        embedding_function=embedding_function,
        collection_name=f"client_{client_id}_knowledge",
        use_jsonb=True,
    )
    client_retriever = client_db.as_retriever(search_kwargs={"k": 15})

    merged = MergedRetriever(retrievers=[base_retriever, client_retriever])

    boosted = TopicBoostedRetriever(
        base_retriever=merged,
        top_k=5,
        boost_factor=0.5,
        patient_conditions=patient_conditions or [],
    )

    print(
        f"[VectorStore] Topic-boosted hybrid retriever | "
        f"client_id={client_id} | conditions={patient_conditions or []}"
    )
    return boosted
