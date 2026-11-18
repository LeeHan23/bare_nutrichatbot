"""
Write each My Heart Coach user their own weekday EKA sets (MHC staging DB),
built from Nutribot's approved EKA content for their conditions + level.
Follows myheart-content-schema.html ("Per-user EKA"): one eka_sets row per
user per weekday (risk_level NULL), items copied per set, BM in the rows,
English in content_item_translations, one content_items row per real piece
of content reused across users.

Per user per weekday (max 3 of each, rotating across their condition groups):
  knowledge  = that day's learning point of each matched K item (Sun = key takeaway)
  activities = that day's micro-action of each matched A item (Sat/Sun = weekend)
  exercises  = catalog exercises from matched E items + level-allowed catalog picks

    python scripts/push_mhc_user_eka.py                 # dry run: translate + preview only
    python scripts/push_mhc_user_eka.py --apply         # write to MHC staging
    python scripts/push_mhc_user_eka.py --remove 12 34  # delete those users' own sets (cascades their logs)

Users who already have own sets are skipped; --replace deletes and rewrites
them, which also deletes their logs of the old items.
"""
import argparse
import hashlib
import json
import math
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

import database as db
import myheart_db
from content_api_router import _feed
from exercise_lookup import list_all, pick_level_exercises
from generate_content import conditions_to_groups
from sample_rulespolicy_week import _loops

DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
PER_DAY = 3
DIFFICULTY = {"Light": 1, "Moderate": 2, "Vigorous": 3, "High": 3}
CACHE_PATH = os.path.join(ROOT, "data", "mhc_bm_cache.json")
MAP_PATH = os.path.join(ROOT, "data", "mhc_content_item_map.json")
PREVIEW_PATH = os.path.join(ROOT, "materials", "mhc_user_eka_preview.json")


def _clean(s, limit=None):
    """Plain text, no 4-byte characters (portal rule), trimmed to the column."""
    s = re.sub(r"[^\u0000-￿]", "", str(s or "")).strip()
    return s[:limit] if limit else s


def _strip_week(title):
    return re.sub(r"^Week \d+\s*[—-]\s*", "", title or "")


def _rotate(items, d):
    """Up to PER_DAY items for weekday index d, rotating so every item shows during the week."""
    n = len(items)
    return [items[(d + j) % n] for j in range(min(PER_DAY, n))]


# ---------------------------------------------------------------------------
# Plan: what each user gets, in English
# ---------------------------------------------------------------------------

def _knowledge_piece(item, d):
    c, mid = item["content"], item["id"]
    pts = c.get("learning_points") or []
    if d < 6 and pts:
        p = pts[d % len(pts)]
        return {"key": f"k{mid}:{d % len(pts)}", "type": "KNOWLEDGE",
                "en": {"title": p.get("point"), "content": f"{p.get('explanation', '')}\n\n{p.get('why_it_matters', '')}"}}
    return {"key": f"k{mid}:takeaway", "type": "KNOWLEDGE",
            "en": {"title": f"Key takeaway: {_strip_week(item['title'])}",
                   "content": f"{c.get('key_takeaway', '')}\n\n{c.get('local_context', '')}"}}


def _activity_piece(item, d):
    c, mid = item["content"], item["id"]
    acts = c.get("micro_actions") or c.get("instructions") or [c.get("description", "")]
    i = min(d, 5) % len(acts)
    action = acts[i].split(":", 1)[1].strip() if re.match(r"^\w+:", acts[i]) else acts[i]
    return {"key": f"a{mid}:{i}", "type": "ACTIVITY",
            "en": {"title": f"{c.get('task_name') or _strip_week(item['title'])}: {action}"}}


def _exercise_pool(user_id, level, e_items):
    """Catalog rows: the E items' own highlights first, then level-allowed picks."""
    import taxonomy
    from exercise_lookup import _parse_allowed_levels
    rules = (taxonomy.LEVEL_EKA_CONSTRAINTS.get(level) or taxonomy.OB_EKA_CONSTRAINTS[level])["exercise"]
    catalog_level = "L2" if level.startswith("OB") else level
    # Approved highlights can still break the level rules (week 42 gave L3 a
    # Moderate cool-down), so every exercise is re-checked here.
    by_key = {(v["exercise_title"], v.get("intensity_tier"), v.get("type")): v
              for v in list_all()
              if v.get("approved", True) and catalog_level in _parse_allowed_levels(v.get("allowed_level"))
              and v.get("type") in rules["types"] and v.get("intensity_tier") in rules["intensity"]}
    pool, seen = [], set()
    highlights = [h for it in e_items for h in it["content"].get("catalog_highlights") or []]
    for h in highlights:
        v = by_key.get((h.get("title"), h.get("intensity_tier"), h.get("type")))
        if v and v["exercise_title"] not in seen:
            seen.add(v["exercise_title"])
            pool.append(v)
    for v in pick_level_exercises(level, seed=user_id, n=8):
        if len(pool) >= 9:
            break
        if v["exercise_title"] not in seen:
            seen.add(v["exercise_title"])
            pool.append(v)
    return pool


def _exercise_piece(v):
    m, s = (v.get("video_duration") or "0:00").split(":")
    secs = (int(m) * 60 + int(s)) * (_loops(v.get("min_loop"), first=True) or 1)
    return {"key": f"ex:{v['exercise_title']}", "type": "EXERCISE",
            "title": _clean(v["exercise_title"], 255), "video_url": v.get("youtube_link"),
            "duration_minutes": min(255, max(1, math.ceil(secs / 60))),
            "difficulty": DIFFICULTY.get(v.get("intensity_tier"))}


def build_plan(session):
    conn = myheart_db._get_connection()
    with conn, conn.cursor() as cur:
        cur.execute("SELECT id, phone_no FROM users WHERE phone_no IS NOT NULL AND phone_no <> ''")
        users = cur.fetchall()
    plan, week = [], None
    for user_id, phone in users:
        p = myheart_db.get_myheart_profile(phone)
        level = p and (p["personalization_level"] or p["onboarding_stage"])
        if not level:
            continue  # OB0 / unknown: the app shows no EKA for them anyway
        groups = conditions_to_groups(p["condition"])
        f = _feed(session, groups, None, True, p["personalization_level"], p["onboarding_stage"])
        week = f["week_number"]
        feed = f["feed"]
        pool = _exercise_pool(user_id, level, feed["E"])
        days = {}
        for d, day in enumerate(DAYS):
            days[day] = {
                "knowledge": [_knowledge_piece(it, d) for it in _rotate(feed["K"], d)],
                "activities": [_activity_piece(it, d) for it in _rotate(feed["A"], d)],
                "exercises": [_exercise_piece(pool[(d * PER_DAY + j) % len(pool)])
                              for j in range(min(PER_DAY, len(pool)))] if pool else [],
            }
        plan.append({"user_id": user_id, "name": p["name"], "level": level, "groups": groups, "days": days})
    return plan, week


# ---------------------------------------------------------------------------
# BM translation (cached; English stays as the EN translation)
# ---------------------------------------------------------------------------

def _hash(en):
    return hashlib.sha1(json.dumps(en, sort_keys=True).encode()).hexdigest()[:12]


_TRANSLATE_PROMPT = """Translate this patient health education content from English to Bahasa Melayu (Malaysia), for a heart-health app.
Keep the meaning exactly. Keep numbers, units and food names. Plain text only: no markdown, no emoji, no added content.
Write standard Malaysian Malay (Bahasa Melayu as used by KKM / Malaysian hospitals), NOT Indonesian. Use these terms:
kidney = buah pinggang (never ginjal); exercise = senaman / bersenam (never olahraga); cycling = berbasikal;
level (blood pressure, sugar, cholesterol) = paras; blood pressure = tekanan darah; blood sugar = gula dalam darah;
heart failure = kegagalan jantung; salt = garam; sodium = natrium; potassium = kalium; doctor = doktor;
dietitian = pegawai dietetik; medicine = ubat; check = periksa; weight = berat badan; week = minggu.
Use natural Malay word order (e.g. "paras LDL yang tinggi", not "tingkat yang tinggi dari LDL").
Return ONLY a JSON object {"items": [...]} whose list has the same number of objects, with the same keys, in the same order."""


def translate(plan):
    from generate_weekly_eka import _call_and_parse
    cache = json.load(open(CACHE_PATH)) if os.path.exists(CACHE_PATH) else {}
    todo = {}
    for u in plan:
        for day in u["days"].values():
            for piece in day["knowledge"] + day["activities"]:
                c = cache.get(piece["key"])
                if not c or c["hash"] != _hash(piece["en"]):
                    todo[piece["key"]] = piece["en"]
    keys = list(todo)

    def _try(batch):
        src = [todo[k] for k in batch]
        prompt = _TRANSLATE_PROMPT + "\n\n" + json.dumps(src, ensure_ascii=False, indent=1)
        for _ in range(2):
            out = _call_and_parse(prompt, 2500)
            items = out.get("items") if isinstance(out, dict) else None
            if (isinstance(items, list) and len(items) == len(src)
                    and all(isinstance(t, dict) and set(t) == set(s) and all(str(t[k]).strip() for k in s)
                            for t, s in zip(items, src))):
                for k, s, t in zip(batch, src, items):
                    cache[k] = {"hash": _hash(s), "bm": t}
                return True
        return False

    for start in range(0, len(keys), 6):
        batch = keys[start:start + 6]
        if not _try(batch):  # a bad batch is usually one awkward piece: retry them one by one
            for k in batch:
                if not _try([k]):
                    print(f"  translation failed for {k}; it stays untranslated and will be skipped")
        json.dump(cache, open(CACHE_PATH, "w"), ensure_ascii=False, indent=1)
        print(f"  translated {min(start + 6, len(keys))}/{len(keys)}", flush=True)
    return cache


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def _content_item(cur, key, ctype, en_title, en_content, item_map, now):
    if key in item_map:
        return item_map[key]
    cur.execute("INSERT INTO content_items (content_type, created_at, updated_at) VALUES (%s,%s,%s)", (ctype, now, now))
    cid = cur.lastrowid
    cur.execute("INSERT INTO content_item_translations (content_item_id, locale, title, content, equipment, media_url, created_at, updated_at) "
                "VALUES (%s,'EN',%s,%s,NULL,NULL,%s,%s)", (cid, _clean(en_title, 255), _clean(en_content) or None, now, now))
    item_map[key] = cid
    return cid


def apply(plan, cache, replace):
    item_map = json.load(open(MAP_PATH)) if os.path.exists(MAP_PATH) else {}
    conn = myheart_db._get_connection()
    written = skipped = 0
    with conn:
        cur = conn.cursor()
        if item_map:  # drop mappings whose content_items row was deleted on their side
            cur.execute(f"SELECT id FROM content_items WHERE id IN ({','.join(['%s'] * len(item_map))})", list(item_map.values()))
            alive = {r[0] for r in cur.fetchall()}
            item_map = {k: v for k, v in item_map.items() if v in alive}
        for u in plan:
            cur.execute("SELECT COUNT(*) FROM eka_sets WHERE user_id = %s", (u["user_id"],))
            if cur.fetchone()[0]:
                if not replace:
                    skipped += 1
                    continue
                cur.execute("DELETE FROM eka_sets WHERE user_id = %s", (u["user_id"],))
            now = int(time.time())
            try:
                for day, items in u["days"].items():
                    cur.execute("INSERT INTO eka_sets (user_id, day_of_week, risk_level, created_at, updated_at) VALUES (%s,%s,NULL,%s,%s)",
                                (u["user_id"], day, now, now))
                    set_id = cur.lastrowid
                    for i, piece in enumerate(p for p in items["knowledge"] if p["key"] in cache):
                        bm = cache[piece["key"]]["bm"]
                        cid = _content_item(cur, piece["key"], "KNOWLEDGE", piece["en"]["title"], piece["en"]["content"], item_map, now)
                        cur.execute("INSERT INTO knowledge_articles (eka_set_id, title, publisher, content, sort_order, created_at, updated_at, content_item_id) "
                                    "VALUES (%s,%s,NULL,%s,%s,%s,%s,%s)",
                                    (set_id, _clean(bm["title"], 255), _clean(bm["content"]), (i + 1) * 10, now, now, cid))
                    for i, piece in enumerate(p for p in items["activities"] if p["key"] in cache):
                        bm = cache[piece["key"]]["bm"]
                        cid = _content_item(cur, piece["key"], "ACTIVITY", piece["en"]["title"], None, item_map, now)
                        cur.execute("INSERT INTO activities (eka_set_id, title, duration_minutes, sort_order, created_at, updated_at, content_item_id) "
                                    "VALUES (%s,%s,NULL,%s,%s,%s,%s)", (set_id, _clean(bm["title"], 255), (i + 1) * 10, now, now, cid))
                    for i, ex in enumerate(items["exercises"]):
                        cid = _content_item(cur, ex["key"], "EXERCISE", ex["title"], None, item_map, now)
                        cur.execute("INSERT INTO exercises (eka_set_id, title, duration_minutes, difficulty, sets_count, repetition_count, "
                                    "equipment, video_url, sort_order, created_at, updated_at, content_item_id) "
                                    "VALUES (%s,%s,%s,%s,NULL,NULL,NULL,%s,%s,%s,%s,%s)",
                                    (set_id, ex["title"], ex["duration_minutes"], ex["difficulty"], ex["video_url"],
                                     (i + 1) * 10, now, now, cid))
                conn.commit()
                written += 1
            except Exception:
                conn.rollback()
                raise
            finally:
                json.dump(item_map, open(MAP_PATH, "w"), indent=1)
    print(f"Wrote own sets for {written} users; skipped {skipped} that already had them.")


def remove(user_ids):
    conn = myheart_db._get_connection()
    with conn, conn.cursor() as cur:
        cur.execute(f"DELETE FROM eka_sets WHERE user_id IS NOT NULL AND user_id IN ({','.join(['%s'] * len(user_ids))})", user_ids)
        print(f"Deleted {cur.rowcount} own sets.")
        conn.commit()


def _preview(plan, cache, week):
    out = []
    for u in plan:
        days = {}
        for day, items in u["days"].items():
            days[day] = {
                "knowledge": [{"bm": cache.get(p["key"], {}).get("bm"), "en": p["en"]} for p in items["knowledge"]],
                "activities": [{"bm": cache.get(p["key"], {}).get("bm", {}).get("title"), "en": p["en"]["title"]} for p in items["activities"]],
                "exercises": [{k: e[k] for k in ("title", "duration_minutes", "difficulty", "video_url")} for e in items["exercises"]],
            }
        out.append({"user_id": u["user_id"], "name": u["name"], "level": u["level"], "groups": u["groups"], "days": days})
    json.dump({"source_week": week, "users": out}, open(PREVIEW_PATH, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--remove", type=int, nargs="+", metavar="USER_ID")
    a = ap.parse_args()
    if a.remove:
        remove(a.remove)
        sys.exit()
    session = db.SessionLocal()
    plan, week = build_plan(session)
    print(f"{len(plan)} users, content from week {week}")
    cache = translate(plan)
    _preview(plan, cache, week)
    missing = {p["key"] for u in plan for d in u["days"].values() for p in d["knowledge"] + d["activities"] if p["key"] not in cache}
    print(f"Preview: {PREVIEW_PATH}  ({len(missing)} pieces untranslated)")
    if a.apply:
        apply(plan, cache, a.replace)
