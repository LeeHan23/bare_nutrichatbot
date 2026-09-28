"""
Unit tests for structured_store.lookup() — pure keyword-scoring logic,
no real spreadsheets loaded (module cache is monkeypatched directly).

Ported from barebones_rag/tests/test_structured_store.py — unchanged.
"""
import structured_store

_FAKE_ROWS = [
    ("products.xlsx / Finalized", "Glucerna TC | adult diabetes | 220 kcal/scp | 9.5g protein"),
    ("products.xlsx / Finalized", "Ensure Plus | adult general | 350 kcal/scp | 13g protein"),
    ("labs.xls / Ref Ranges", "Potassium | Adults | 3.5-5.0 mmol/L"),
    ("labs.xls / Ref Ranges", "Sodium | Adults | 135-145 mmol/L"),
]


def _patch_rows(monkeypatch, rows):
    monkeypatch.setattr(structured_store, "_rows", rows)


def test_lookup_matches_query_tokens(monkeypatch):
    _patch_rows(monkeypatch, _FAKE_ROWS)
    # "Glucerna" + "protein" both match row 1 (score 2); "protein" alone
    # matches row 2 (score 1) — top_k=1 should surface the stronger match.
    results = structured_store.lookup("what's the protein content of Glucerna", top_k=1)
    assert results == ["[products.xlsx / Finalized] Glucerna TC | adult diabetes | 220 kcal/scp | 9.5g protein"]


def test_lookup_respects_top_k(monkeypatch):
    _patch_rows(monkeypatch, _FAKE_ROWS)
    results = structured_store.lookup("Adults reference mmol", top_k=1)
    assert len(results) == 1


def test_lookup_no_match_returns_empty_list(monkeypatch):
    _patch_rows(monkeypatch, _FAKE_ROWS)
    assert structured_store.lookup("weather forecast tomorrow", top_k=3) == []


def test_lookup_ignores_very_short_tokens(monkeypatch):
    _patch_rows(monkeypatch, _FAKE_ROWS)
    # "of" (len 2) is excluded; "the" (len 3) is kept but doesn't appear as
    # a substring in any fake row, so this still resolves to no match.
    assert structured_store.lookup("of the", top_k=3) == []


def test_lookup_matches_three_letter_abbreviations(monkeypatch):
    # len>3 used to exclude exactly 3-char tokens — real abbreviations like
    # "RTD" (ready-to-drink) are exactly this length, and excluding them
    # meant a query naming a specific RTD product couldn't be distinguished
    # from any other product sharing its brand name.
    rows = _FAKE_ROWS + [
        ("products.xlsx / Finalized", "Ensure RTD | RTD formula | 266 kcal/scp | 9.3g protein"),
    ]
    _patch_rows(monkeypatch, rows)
    results = structured_store.lookup("Ensure RTD kcal", top_k=1)
    assert results == ["[products.xlsx / Finalized] Ensure RTD | RTD formula | 266 kcal/scp | 9.3g protein"]


def test_lookup_formats_label_and_text(monkeypatch):
    _patch_rows(monkeypatch, _FAKE_ROWS)
    results = structured_store.lookup("Potassium reference range", top_k=1)
    assert results[0] == "[labs.xls / Ref Ranges] Potassium | Adults | 3.5-5.0 mmol/L"


# ── _find_header_rows / _load_tables — column-position alignment ───────────
#
# Regression coverage for a real bug: a row with a gap in an early column
# (e.g. a missing "oz/scp" value) used to shift every later value one
# column left after dropping nulls, so "Protein" ended up labeled "Energy"
# and vice versa. Fixed by pairing header[i] with row[i] positionally,
# skipping only empty cells rather than compacting the row first.


def test_find_header_rows_skips_single_cell_title_row():
    # Rows are equal-width, as pandas always returns them (a DataFrame has
    # one fixed column count) — the title row's other cells are just blank,
    # not absent.
    cell_rows = [
        ["REFERENCE RANGE FOR ROUTINE TESTS", "", "", ""],
        ["NO", "ANALYTE", "AGE", "METHOD"],
        ["1", "Sodium", "Adults", "ISE"],
    ]
    headers, start = structured_store._find_header_rows(cell_rows)
    assert headers == ["NO", "ANALYTE", "AGE", "METHOD"]
    # The data row ("1 | Sodium | Adults | ISE") also has a low numeric
    # ratio (only "1") so _looks_like_header alone would wrongly swallow
    # it too — fills_gap must stop the merge here since every column the
    # data row fills is already claimed by the header.
    assert start == 2


def test_find_header_rows_returns_none_when_no_header_like_row():
    cell_rows = [["1", "2", "3"], ["4", "5", "6"]]
    assert structured_store._find_header_rows(cell_rows) is None


def test_find_header_rows_merges_consecutive_split_header_rows():
    # A group header row, then a sub-label row beneath it — the real
    # "Data" sheet pattern (e.g. "Nutrition info" over "Energy | Prot").
    # Earlier row's label wins per column; later row fills the gaps.
    cell_rows = [
        ["Type", "Product name", "", "", "Nutrition info", ""],
        ["", "", "Weight (g)", "Oz", "Energy (kcal)", "Prot (g)"],
        ["adult", "Ensure", "10", "45", "266", "9.3"],
    ]
    headers, start = structured_store._find_header_rows(cell_rows)
    assert headers == ["Type", "Product name", "Weight (g)", "Oz", "Nutrition info", "Prot (g)"]
    assert start == 2


def test_load_tables_keeps_labels_aligned_across_a_row_with_a_gap(tmp_path, monkeypatch):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Finalized"
    ws.append(["Type", "Formula", "g/scp", "oz/scp", "Energy kcal/scp", "Protein g/scp"])
    # "oz/scp" is genuinely missing on this row — the real-world case that
    # broke the old dropna-then-join approach.
    ws.append(["adult diabetes", "Glucerna TC", "10.4", None, "45.6", "2.02904"])
    wb.save(tmp_path / "products.xlsx")

    monkeypatch.setattr(structured_store, "STRUCTURED_DATA_DIR", str(tmp_path))
    rows = structured_store._load_tables()

    assert len(rows) == 1
    _, text = rows[0]
    assert "Energy kcal/scp: 45.6" in text
    assert "Protein g/scp: 2.02904" in text
    assert "oz/scp" not in text  # the missing cell contributes no pair at all


def test_load_tables_skips_noise_sheets(tmp_path, monkeypatch):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Template"
    ws.append(["Type", "Product name"])
    ws.append(["example", "example product"])
    wb.save(tmp_path / "products.xlsx")

    monkeypatch.setattr(structured_store, "STRUCTURED_DATA_DIR", str(tmp_path))
    assert structured_store._load_tables() == []
