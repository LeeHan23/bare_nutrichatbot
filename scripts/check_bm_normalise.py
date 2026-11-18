"""Sentence-integrity check for bm_normalise.fix() over every stored bot reply.

Automatic checks (any failure exits 1):
  - English / non-Malay replies come back byte-identical
  - every changed reply keeps the same digits, punctuation and sentence count
  - no doubled word is introduced ("anda anda")
  - no listed Indonesian word survives
Then writes a before/after sheet of every changed sentence for a native
BM speaker to read: eval/results/bm_normalise_review.md

Run: .venv/bin/python scripts/check_bm_normalise.py
"""
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text  # noqa: E402

import bm_normalise as bmn  # noqa: E402
import database as db  # noqa: E402

OUT = "eval/results/bm_normalise_review.md"
SENT = re.compile(r"(?<=[.!?])\s+|\n+")
DOUBLE = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)


def sig(s, pat):
    return re.findall(pat, s)


def main():
    s = db.SessionLocal()
    rows = [r[0] for r in s.execute(text(
        "select content from chat_messages where role='assistant' order by created_at")).fetchall()]
    s.close()

    fails, changed, hits = [], [], collections.Counter()
    seen = set()
    for before in rows:
        after = bmn.fix(before)
        if not bmn.looks_malay(before):
            if after != before:
                fails.append(("non-Malay reply changed", before[:120]))
            continue
        if after == before:
            continue
        for name, pat in (("digits", r"\d+"), ("punctuation", r"[^\w\s]")):
            if sig(before, pat) != sig(after, pat):
                fails.append((f"{name} changed", before[:120]))
        if len(SENT.split(before.strip())) != len(SENT.split(after.strip())):
            fails.append(("sentence count changed", before[:120]))
        new_doubles = set(m.lower() for m in DOUBLE.findall(after)) - set(m.lower() for m in DOUBLE.findall(before))
        if new_doubles:
            fails.append((f"doubled word {sorted(new_doubles)}", after[:120]))
        if bmn._RE.search(after):
            fails.append(("listed word survived", after[:120]))
        for m in bmn._RE.finditer(before):
            hits[m.group(0).lower()] += 1
        for sb, sa in zip(SENT.split(before.strip()), SENT.split(after.strip())):
            if sb != sa and sb not in seen:
                seen.add(sb)
                changed.append((sb, sa))

    malay = sum(bmn.looks_malay(r) for r in rows)
    lines = [
        "# bm_normalise review sheet",
        "",
        f"{len(rows)} stored replies, {malay} read as Malay, {len(changed)} distinct sentences changed.",
        "Read each **after** line: is it correct, natural Bahasa Malaysia? Mark any that are worse than **before**.",
        "",
        "## Words swapped (count)",
        "",
        ", ".join(f"{w} → {bmn.PAIRS[w]} ({n})" for w, n in hits.most_common()),
        "",
        "## Changed sentences",
        "",
    ]
    for i, (sb, _) in enumerate(changed, 1):
        lines += [f"{i}. before: {bmn._RE.sub(lambda m: f'**{m.group(0)}**', sb)}",
                  f"   after: {bmn._RE.sub(lambda m: f'**{bmn._swap(m)}**', sb)}", ""]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("\n".join(lines))

    print(f"replies={len(rows)} malay={malay} changed_sentences={len(changed)} swaps={sum(hits.values())}")
    print("top swaps:", ", ".join(f"{w}({n})" for w, n in hits.most_common(15)))
    print(f"review sheet: {OUT}")
    if fails:
        print(f"FAIL {len(fails)}:")
        for why, t in fails[:20]:
            print(f"  {why}: {t!r}")
        sys.exit(1)
    print("all integrity checks passed")


if __name__ == "__main__":
    main()
