"""
Sample one week of EKA content in the RulesPolicy "Task Generation Engine"
format (MyHeartCoach_RulesPolicyTables_v2.xlsx, Prompt tab), plus
`contraindications` from its EKA schema tab. For review only: writes
materials/samples/eka_week{N}_rulespolicy.{json,xlsx}, never the database.

Reuses generate_weekly_eka.py's weekly topics, L0-L3/OB1-3 variants, RAG
retrieval and safety rules; only the output shape changes.

Exercise tasks are built around ONE approved catalog exercise each: type,
intensity, duration, frequency and video link come from the catalog in code;
the LLM writes description/instructions/stop conditions/contraindications/
safety note, with instructions based only on the catalog's own explanation.

    python scripts/sample_rulespolicy_week.py --week 48
    python scripts/sample_rulespolicy_week.py --week 48 --group CKD --type E   # quick test
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

import taxonomy
from exercise_lookup import pick_level_exercises
from generate_weekly_eka import (build_eka_cases, _expand_variants, _retrieve_chunks,
                                 _call_and_parse, _SAFETY_GUARDRAILS)

_RULES = {
    "E": "Stop conditions and safety note are mandatory. Use simple language. No medical claims. "
         "No diagnostic advice. No competitive exercise language.",
    "K": "Maximum 3 key points. Easy reading level. Actionable tip must be lifestyle-based. "
         "No treatment recommendations. No medication adjustment advice.",
    "A": "Must be ADL-focused when required. Non-structured activities preferred for higher-risk users. "
         "Motivational but not demanding. No exercise prescription in Activity tasks.",
}


def _header(v):
    return (f"TOPIC: {v['prompt_topic']}\nCONDITION GROUP: {v['group']}\n"
            f"LEVEL: {v['personalization_level'] or v['onboarding_stage']}\n\n"
            f"{_SAFETY_GUARDRAILS}\nLEVEL RULES (mandatory, override everything else):\n{v['guidance']}\n")


def _rules(v):
    return (taxonomy.LEVEL_EKA_CONSTRAINTS.get(v["personalization_level"] or "")
            or taxonomy.OB_EKA_CONSTRAINTS[v["onboarding_stage"]])


def _mmss(secs):
    return f"{secs // 60}:{secs % 60:02d}"


def _loops(v, first):
    """Catalog loop counts come as 2.0, '1–2', '1900-01-03 00:00:00' (an Excel
    day serial: 3) or '❌' (none)."""
    import re
    if isinstance(v, (int, float)):
        return int(v)
    if not isinstance(v, str) or "❌" in v:
        return None
    m = re.match(r"1900-01-(\d\d)", v)
    if m:
        return int(m.group(1))
    nums = [int(n) for n in re.findall(r"\d+", v)]
    return (nums[0] if first else nums[-1]) if nums else None


def _dose(ex, rules):
    """(duration, frequency) from video length x loops. The catalog's own
    total_duration is unreliable (19 rows in a broken h:m:s form, 39 blank)."""
    m, s = (ex.get("video_duration") or "0:00").split(":")
    video = int(m) * 60 + int(s)
    lo, hi = _loops(ex.get("min_loop"), first=True) or 1, _loops(ex.get("max_loop"), first=False) or 1
    cap_loops = rules.get("frequency_max_loops_per_day")
    if cap_loops:
        hi = min(hi, cap_loops)
    lo = min(lo, hi)
    cap_secs = (rules.get("duration_max_minutes") or 0) * 60
    hi_secs = min(video * hi, cap_secs) if cap_secs else video * hi
    duration = _mmss(video * lo) if lo == hi else f"{_mmss(video * lo)}-{_mmss(hi_secs)}"
    loops = f"{lo} loop" + ("s" if lo > 1 else "") if lo == hi else f"{lo}-{hi} loops"
    freq = f"{loops} of the video a day (no more than {cap_loops} loops a day)" if cap_loops else f"{loops} of the video per session"
    return duration, freq


def _match_title(title, by_title):
    """The model sometimes echoes the list line ('0041 – Ankle sliding (Strength/
    Resistance, Light, ...)') or drops the number prefix ('Seated side-to-side
    groin stretch'). Accept those, but only when exactly one listed exercise fits
    best. Catalog titles can contain brackets themselves, so match by prefix."""
    import re
    if not title:
        return None
    if title in by_title:
        return by_title[title]
    best, hits = 0, []
    for t, v in by_title.items():
        for name in (t, re.sub(r"^.*?–\s+", "", t)):
            if title == name or title.startswith(name + " ("):
                if len(name) > best:
                    best, hits = len(name), [v]
                elif len(name) == best and v not in hits:
                    hits.append(v)
    return hits[0] if len(hits) == 1 else None


def _exercise(v, seed):
    level = v["personalization_level"] or v["onboarding_stage"]
    candidates = pick_level_exercises(level, seed, n=8)
    if not candidates:
        return {"type": "exercise", "error": f"no catalog exercise allowed for {level}"}
    rules = _rules(v)["exercise"]
    cand_text = "\n".join(
        f"- {c['exercise_title']} ({c['type']}, {c['intensity_tier']}, {c.get('body_focus')}): {c.get('explanation')}"
        for c in candidates)
    prompt = f"""You are a cardiovascular health task recommendation engine for a Malaysian programme. Generate ONE exercise task.

{_header(v)}
ALLOWED EXERCISES (approved video catalog; each has a Malay explanation of how it is done). Choose the ONE that best fits the topic and copy its title exactly:
{cand_text}

RULES: {_RULES['E']}
- "instructions": 3-5 short steps in English, based ONLY on the chosen exercise's explanation. Add nothing it doesn't say.
- "stop_conditions": symptoms that mean stop immediately ({rules.get('stop_conditions')}).
- "contraindications": situations where this exercise should NOT be done at all (e.g. a recent cardiac event not yet cleared by the doctor, unstable chest pain, acute illness, an injury to the body part it uses).
- "progression": {"write exactly: Not allowed at this level." if rules.get("progression") == "forbidden" else "one cautious, optional way to make it slightly harder, within the level's intensity limits."}

Return ONLY valid JSON, no prose, no markdown fences:
{{"title": "<exact title from the list>",
  "description": "1-2 sentences: what this exercise is and why it helps, tied to the topic",
  "instructions": ["step 1", "step 2", "step 3"],
  "stop_conditions": ["...", "...", "..."],
  "contraindications": ["...", "..."],
  "safety_note": "posture, breathing, hydration reminder{' plus a medical disclaimer' if rules.get('safety_note') == 'medical disclaimer' else ''}",
  "progression": "..."}}"""
    out = _call_and_parse(prompt, 800)
    if out.get("parse_error"):
        return {"type": "exercise", **out}
    by_title = {c["exercise_title"]: c for c in candidates}
    ex = _match_title(out.get("title"), by_title)
    if not ex:  # invented or mangled title: instructions can't be trusted either
        return {"type": "exercise", "error": f"model chose a title not in the catalog: {out.get('title')!r}"}
    duration, frequency = _dose(ex, rules)
    task = {"type": "exercise", "title": ex["exercise_title"], "description": out.get("description"),
            "exercise_type": ex["type"], "intensity": ex["intensity_tier"],
            "duration": duration, "frequency": frequency,
            "instructions": out.get("instructions") or [], "stop_conditions": out.get("stop_conditions") or [],
            "contraindications": out.get("contraindications") or [], "safety_note": out.get("safety_note"),
            "progression": out.get("progression"), "video_url": ex.get("youtube_link")}
    if rules.get("progression") == "forbidden":
        task["progression"] = "Not allowed at this level."
    return task


def _knowledge(v, chunks):
    prompt = f"""You are a cardiovascular health task recommendation engine for a Malaysian programme. Generate ONE knowledge task.

{_header(v)}
CLINICAL EVIDENCE:
{chunks or "No guideline chunks available; use well-established patient education only."}

RULES: {_RULES['K']}

Return ONLY valid JSON, no prose, no markdown fences:
{{"title": "short task title", "topic": "the subject being explained",
  "key_points": ["core fact 1", "core fact 2", "core fact 3"],
  "actionable_tip": "one safe, lifestyle-based action",
  "warning_signs": "symptoms or signals that need caution or medical attention"}}"""
    out = _call_and_parse(prompt, 600)
    if not out.get("parse_error"):
        out["key_points"] = (out.get("key_points") or [])[:3]
    return {"type": "knowledge", **out}


def _activity(v):
    prompt = f"""You are a cardiovascular health task recommendation engine for a Malaysian programme. Generate ONE daily activity task.

{_header(v)}
RULES: {_RULES['A']}

Return ONLY valid JSON, no prose, no markdown fences:
{{"title": "short task title", "suggested_activity": "the daily-life movement or habit",
  "frequency": "how often", "reminder_or_nudge": "one motivational, non-pressuring prompt",
  "adaptation_tip": "how to adjust for fatigue, pain or limitation"}}"""
    return {"type": "activity", **_call_and_parse(prompt, 400)}


_FIELDS = {
    "E": ["title", "description", "exercise_type", "intensity", "duration", "frequency", "instructions",
          "stop_conditions", "contraindications", "safety_note", "progression", "video_url"],
    "K": ["title", "topic", "key_points", "actionable_tip", "warning_signs"],
    "A": ["title", "suggested_activity", "frequency", "reminder_or_nudge", "adaptation_tip"],
}


def _write_excel(items, path):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    wb = Workbook()
    wb.remove(wb.active)
    for ctype, name in (("E", "Exercise"), ("K", "Knowledge"), ("A", "Activity")):
        ws = wb.create_sheet(name)
        cols = ["group", "level", "week topic"] + _FIELDS[ctype]
        ws.append(cols)
        for c in ws[1]:
            c.font = Font(bold=True)
        for it in (i for i in items if i["content_type"] == ctype):
            t = it["task"]
            ws.append([it["group"], it["level"], it["week_topic"]] + [
                "\n".join(f"• {x}" for x in t.get(f)) if isinstance(t.get(f), list) else t.get(f)
                for f in _FIELDS[ctype]])
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 40
            for c in col:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A2"
    wb.save(path)


def main(week, group=None, ctype=None, client_id=4):
    cases = [c for c in build_eka_cases(week)
             if (not group or c["group"] == group) and (not ctype or c["content_type"] == ctype)]
    variants = [v for c in cases for v in _expand_variants(c)]
    out_dir = os.path.join(ROOT, "materials", "samples")
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.join(out_dir, f"eka_week{week}_rulespolicy" + (f"_{group}" if group else "") + (f"_{ctype}" if ctype else ""))
    items = []
    for i, v in enumerate(variants, 1):
        level = v["personalization_level"] or v["onboarding_stage"]
        print(f"[{i}/{len(variants)}] {v['group']} / {v['content_type']} / {level}", flush=True)
        try:
            if v["content_type"] == "E":
                task = _exercise(v, seed=i)
            elif v["content_type"] == "K":
                task = _knowledge(v, _retrieve_chunks(v["rag_query"], client_id))
            else:
                task = _activity(v)
        except Exception as e:
            task = {"error": str(e)}
        items.append({"group": v["group"], "content_type": v["content_type"], "level": level,
                      "week_number": week, "week_topic": v["prompt_topic"], "task": task})
        json.dump(items, open(stem + ".json", "w"), ensure_ascii=False, indent=1)  # save as we go
    _write_excel(items, stem + ".xlsx")
    bad = sum(1 for it in items if it["task"].get("parse_error") or it["task"].get("error"))
    print(f"Done: {len(items)} tasks, {bad} failed -> {stem}.json / .xlsx")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--week", type=int, required=True)
    p.add_argument("--group")
    p.add_argument("--type", dest="ctype", choices=["E", "K", "A"])
    a = p.parse_args()
    main(a.week, a.group, a.ctype)
