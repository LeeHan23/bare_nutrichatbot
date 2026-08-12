"""Self-check for grounding general exercise Q&A in the approved video
catalog (exercise_lookup.list_exercise_samples_for_level,
rag._build_exercise_catalog_block, and the broadened exercise component
detection in vector_store.COMPONENT_HINTS).
Run: python scripts/test_exercise_catalog.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exercise_lookup import list_exercise_samples_for_level
from rag import _build_exercise_catalog_block, _build_qwen_prompt
from vector_store import detect_query_component

# No level -> nothing (err on the side of no grounded claims)
assert list_exercise_samples_for_level(None) == []
assert _build_exercise_catalog_block(None) == ""
assert _build_exercise_catalog_block({}) == ""

# A real level returns a capped, deduped-per-type sample with no youtube link
samples = list_exercise_samples_for_level("L2", per_type=3)
assert samples, "expected at least one L2-eligible exercise"
assert all("youtube_url" not in s and "youtube_link" not in s for s in samples)
by_type = {}
for s in samples:
    by_type[s["type"]] = by_type.get(s["type"], 0) + 1
assert all(n <= 3 for n in by_type.values()), by_type

block = _build_exercise_catalog_block({"personalization_level": "L2"})
assert block and samples[0]["title"] in block

# The prompt actually includes the catalog section for component=exercise,
# and omits it for a non-exercise component.
prompt_with = _build_qwen_prompt(
    "What exercise should I do?", "Conditions: Hypertension", "digest", "",
    {"personalization_level": "L2"}, True, "", component="exercise",
)
assert "## Approved Exercise Catalog" in prompt_with

prompt_without = _build_qwen_prompt(
    "What should I eat for breakfast?", "Conditions: Hypertension", "digest", "",
    {"personalization_level": "L2"}, True, "", component=None,
)
assert "## Approved Exercise Catalog" not in prompt_without

# Broadened intent detection actually routes to the exercise component
for q in ["What exercise should I do for my heart?", "What type of exercise is safe for me?", "Senaman apa yang sesuai untuk saya?"]:
    assert detect_query_component(q) == "exercise", q

# Still no false positives on plain nutrition questions
for q in ["What should I eat for breakfast?", "Can I eat bananas with CKD?"]:
    assert detect_query_component(q) != "exercise", q

print("ALL CHECKS PASSED")
