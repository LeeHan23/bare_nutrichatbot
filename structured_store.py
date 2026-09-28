"""
Structured lookup source for the context engine — reference spreadsheets
(product nutrient tables, lab reference ranges) queried by row, not chunked
and embedded like prose.

Real files here are messy (merged header cells, section titles baked into
row 0, inconsistent columns per sheet) — see spike output in the plan.
Rather than infer a schema per sheet, every row is flattened to a single
text blob and matched by keyword overlap. Simpler and robust to the mess.

Ported from barebones_rag/structured_store.py — logic unchanged.
"""
import glob
import os

from dotenv import load_dotenv

load_dotenv()

STRUCTURED_DATA_DIR = os.getenv("STRUCTURED_DATA_DIR", "")

# Sheet names that are administrative/instructional, not reference data
# (a blank fill-in-the-blank template, product photo captions, a credits
# note) — including them adds pure noise, no real lookup value.
#
# "data" is a project-local addition (this repo's product-list workbooks,
# e.g. NS_list_nutrition_support_2020.xlsx, ONS Product List_2021_Revised.xlsx):
# their "Finalized" sheet is computed via formulas FROM "Data" — including
# both would duplicate every product under two different column layouts.
_NOISE_SHEETS = {"template", "credits", "product photos", "data"}

_rows: list[tuple[str, str]] | None = None  # (label, flattened row text)


def _clean(v) -> str:
    s = str(v).strip() if v is not None else ""
    return "" if s == "nan" else s


def _is_numeric(s: str) -> bool:
    try:
        float(s.replace(",", ""))
        return True
    except ValueError:
        return False


def _looks_like_header(cells: list[str]) -> bool:
    """At least 3 filled cells, mostly non-numeric."""
    filled = [c for c in cells if c]
    if len(filled) < 3:
        return False
    numeric = sum(1 for c in filled if _is_numeric(c))
    return numeric / len(filled) < 0.3


def _find_header_rows(cell_rows: list[list[str]]) -> tuple[list[str], int] | None:
    """Scan the first few rows for header row(s), merge them, and return
    (merged_headers, first_data_row_index) — or None if no header found.

    Real sheets here often lead with a title row (one merged cell) before
    the actual header, and some split column labels across two consecutive
    rows (a group header, then per-column sub-labels beneath it — e.g.
    "Nutrition information" over "Energy (kcal) | Prot (g) | ..."). Both
    get consumed as header rather than leaking into the data with garbage
    labels — earlier row's label wins per column, later rows just fill
    columns the earlier row left blank.
    """
    start = None
    for i, cells in enumerate(cell_rows[:5]):
        if _looks_like_header(cells):
            start = i
            break
    if start is None:
        return None

    merged = list(cell_rows[start])
    end = start + 1
    while end < len(cell_rows) and _looks_like_header(cell_rows[end]):
        candidate = cell_rows[end]
        # A genuine continuation row fills columns the header-so-far left
        # blank. Without this check, a real first DATA row that happens to
        # be mostly text (one numeric id column, say) also passes
        # _looks_like_header and gets wrongly swallowed as more header.
        fills_gap = any(
            val and (col_i >= len(merged) or not merged[col_i])
            for col_i, val in enumerate(candidate)
        )
        if not fills_gap:
            break
        for col_i, val in enumerate(candidate):
            if col_i >= len(merged):
                merged.append(val)
            elif not merged[col_i]:
                merged[col_i] = val
        end += 1
    return merged, end


def _load_tables() -> list[tuple[str, str]]:
    import pandas as pd

    rows: list[tuple[str, str]] = []
    if not STRUCTURED_DATA_DIR or not os.path.isdir(STRUCTURED_DATA_DIR):
        return rows

    paths = glob.glob(os.path.join(STRUCTURED_DATA_DIR, "*.xls*"))
    for path in paths:
        filename = os.path.basename(path)
        if "copy of" in filename.lower():
            continue  # known duplicate NS-list copies

        engine_kwargs = {"read_only": True} if path.lower().endswith(".xlsx") else {}
        try:
            sheets = pd.read_excel(
                path, sheet_name=None, header=None, dtype=str, engine_kwargs=engine_kwargs
            )
        except Exception as e:
            print(f"[structured_store] skip {filename}: {e}")
            continue

        for sheet_name, df in sheets.items():
            if sheet_name.strip().lower() in _NOISE_SHEETS:
                continue
            label = f"{filename} / {sheet_name}"

            cell_rows = [[_clean(c) for c in r] for r in df.itertuples(index=False, name=None)]
            found = _find_header_rows(cell_rows)
            headers, start = found if found else (None, 0)

            for cells in cell_rows[start:]:
                # Pair by column position (not by compacted non-null index) so a
                # row missing an earlier column doesn't shift every later value
                # into the wrong label — this was the actual cause of models
                # reading the wrong number off rows with uneven column counts.
                pairs = []
                for col_i, val in enumerate(cells):
                    if not val:
                        continue
                    label_txt = headers[col_i] if headers and col_i < len(headers) else ""
                    pairs.append(f"{label_txt}: {val}" if label_txt else val)
                if pairs:
                    rows.append((label, " | ".join(pairs)))

    return rows


def _get_rows() -> list[tuple[str, str]]:
    global _rows
    if _rows is None:
        _rows = _load_tables()
        print(f"[structured_store] loaded {len(_rows)} rows from {STRUCTURED_DATA_DIR}")
    return _rows


def lookup(query: str, top_k: int = 3) -> list[str]:
    """Return up to top_k rows whose text best overlaps the query's keywords.

    Matches are IDF-weighted (1/document_frequency, computed per-query over
    the matched tokens) so a rare, specific term (e.g. a product name
    appearing in one row) outweighs a generic term that recurs across many
    rows (e.g. "protein" showing up in dozens of lab-test names) — plain
    match-count scoring let generic terms drown out the exact match this
    source exists to find.
    """
    # >=3 (not >3) so abbreviations like "RTD" stay matchable — excluding
    # them meant queries about e.g. "Ensure RTD" couldn't distinguish that
    # product from any other "Ensure X" variant. IDF weighting already
    # keeps generic 3-letter words (the/and/for) from dominating, since
    # they recur in nearly every row.
    tokens = {w for w in query.lower().split() if len(w) >= 3}
    if not tokens:
        return []

    rows = _get_rows()
    lowered = [(label, text, text.lower()) for label, text in rows]
    doc_freq = {t: sum(1 for _, _, tl in lowered if t in tl) for t in tokens}

    scored = []
    for label, text, text_lower in lowered:
        score = sum(1.0 / doc_freq[t] for t in tokens if t in text_lower)
        if score > 0:
            scored.append((score, label, text))

    # ponytail: linear scan over all rows per query — fine at this size
    # (low hundreds to low thousands of rows); swap for an indexed/fuzzy
    # match if the structured corpus grows a lot.
    scored.sort(key=lambda x: -x[0])
    return [f"[{label}] {text}" for _, label, text in scored[:top_k]]
