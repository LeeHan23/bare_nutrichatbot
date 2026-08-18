"""
Smoke test for the Component-taxonomy retrieval additions in vector_store.py.

No DB needed — exercises detect_query_component() directly and the
TopicBoostedRetriever gate logic against fake Documents.

    python scripts/test_component_detection.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.documents import Document

from vector_store import detect_query_component, TopicBoostedRetriever
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun


def test_detect_query_component():
    # Confident non-nutrition matches
    assert detect_query_component("Should I stop my medication for blood pressure?") == "medication"
    assert detect_query_component("I want to quit smoking, any tips?") == "tobacco_nicotine_alcohol"
    assert detect_query_component("Saya nak berhenti merokok") == "tobacco_nicotine_alcohol"
    assert detect_query_component("I am stressed about my diagnosis") == "psychosocial"
    assert detect_query_component("Can you show me an exercise video?") == "exercise"
    assert detect_query_component("How many steps should I walk daily?") == "physical_activity"
    assert detect_query_component("What is a heart attack?") == "foundations"

    # Dietary-framed condition questions must NOT be gated (regression guard —
    # these are today's live Nutrition traffic, all backed by
    # doc_components=["nutrition"] chunks; gating them would zero out
    # working retrieval).
    assert detect_query_component("What can I eat if I have hypertension?") is None
    assert detect_query_component("Is banana safe for CKD patients?") is None
    assert detect_query_component("What foods should a diabetic avoid?") is None
    assert detect_query_component("Best breakfast for high cholesterol?") is None

    # No signal at all
    assert detect_query_component("Hello, how are you?") is None
    print("test_detect_query_component: OK")


class _FakeBaseRetriever(BaseRetriever):
    docs: list

    def _get_relevant_documents(self, query, *, run_manager: CallbackManagerForRetrieverRun):
        return self.docs


def test_component_gate():
    docs = [
        Document(page_content="med chunk", metadata={"doc_components": ["medication"]}),
        Document(page_content="nutrition chunk", metadata={"doc_components": ["nutrition"]}),
        Document(page_content="legacy chunk, no tag", metadata={}),
    ]
    base = _FakeBaseRetriever(docs=docs)

    # NOTE: patient_conditions is passed explicitly everywhere below —
    # relying on its default_factory=list hits a pre-existing pydantic v1/v2
    # Field-mixing quirk in this class unrelated to this feature (the real
    # production entry point, get_retriever(), always passes it explicitly
    # too, so this never fires live).

    # No component set -> no filtering, all 3 survive (truncated to top_k)
    retriever = TopicBoostedRetriever(base_retriever=base, top_k=5, patient_conditions=[], component=None)
    result = retriever.invoke("hello")
    assert len(result) == 3, f"expected 3 unfiltered, got {len(result)}"

    # component="nutrition" -> medication-only chunk excluded, legacy chunk kept
    retriever = TopicBoostedRetriever(base_retriever=base, top_k=5, patient_conditions=[], component="nutrition")
    result = retriever.invoke("hello")
    contents = {d.page_content for d in result}
    assert contents == {"nutrition chunk", "legacy chunk, no tag"}, contents

    # component="medication" with no medication content available except the
    # tagged one and the legacy (unscoped) chunk
    retriever = TopicBoostedRetriever(base_retriever=base, top_k=5, patient_conditions=[], component="medication")
    result = retriever.invoke("hello")
    contents = {d.page_content for d in result}
    assert contents == {"med chunk", "legacy chunk, no tag"}, contents

    print("test_component_gate: OK")


def test_trust_boost_ranks_above_raw_chunk_at_adjacent_rank():
    # trust_boost (0.3) is meant to close a small rank gap, not override a
    # huge embedding-similarity lead — so compare two candidates at adjacent
    # ranks (base_score gap 0.5-0.333=0.167 < 0.3 boost) with equal topic
    # overlap: the approved chunk should still win despite ranking lower.
    # doc_topics cover the full matched tag set (hypertension / hypertension
    # management / blood pressure) so overlap_ratio is 1.0 for both — the
    # denominator is len(query_topics), not len(doc_topics), so a partial
    # tag list would dilute the comparison.
    full_tags = ["hypertension", "hypertension management", "blood pressure"]
    docs = [
        Document(page_content="unrelated top hit", metadata={"doc_topics": []}),
        Document(
            page_content="raw pdf chunk",
            metadata={"doc_topics": full_tags},
        ),
        Document(
            page_content="approved chunk",
            metadata={"doc_topics": full_tags, "trust_tier": "clinical_approved"},
        ),
    ]
    base = _FakeBaseRetriever(docs=docs)
    retriever = TopicBoostedRetriever(base_retriever=base, top_k=2, boost_factor=0.5, patient_conditions=[])
    result = retriever.invoke("what should I know about hypertension?")
    assert result[0].page_content == "approved chunk", [d.page_content for d in result]
    print("test_trust_boost_ranks_above_raw_chunk_at_adjacent_rank: OK")


if __name__ == "__main__":
    test_detect_query_component()
    test_component_gate()
    test_trust_boost_ranks_above_raw_chunk_at_adjacent_rank()
    print("All component-detection smoke tests passed.")
