"""Phase 2: whole-history check across several doctors.
Builds on engine.py (unchanged). ALL medical data is ILLUSTRATIVE: a pharmacist must verify it."""
import re
from datetime import timedelta
from difflib import SequenceMatcher

from engine import BRANDS, ALIAS_TO_BRAND, SEV_ORDER, parse_line, match_brand, analyse

# ---------- 1. KIDNEY RULES (placeholders for pharmacist review) ----------
# ingredient -> rules in ASCENDING order of creatinine clearance (mL/min): (below, severity, message)
_NSAID = [(30, "CRITICAL", "Kidney clearance is below 30 mL/min: NSAIDs are usually avoided."),
          (60, "MODERATE", "Reduced kidney function: use NSAIDs with caution and monitor.")]
RENAL_RULES = {
    "metformin": [(30, "CRITICAL", "Metformin is not recommended below 30 mL/min kidney clearance."),
                  (45, "MAJOR", "Kidney clearance below 45 mL/min: metformin dose needs review.")],
    "ibuprofen": _NSAID, "diclofenac": _NSAID, "aceclofenac": _NSAID,
    "amoxicillin": [(30, "MAJOR", "Kidney clearance below 30 mL/min: amoxicillin dose needs adjusting.")],
    "clavulanic acid": [(30, "MAJOR", "Kidney clearance below 30 mL/min: amoxicillin-clavulanate dose needs adjusting.")],
    "hydrochlorothiazide": [(30, "MODERATE", "May work poorly when kidney clearance is below 30 mL/min.")],
}

def creatinine_clearance(age, weight_kg, scr_mg_dl, female):
    """Cockcroft-Gault estimate in mL/min."""
    crcl = ((140 - age) * weight_kg) / (72 * scr_mg_dl)
    return crcl * 0.85 if female else crcl

def parse_kidney_readings(text):
    """Lines like '2026-10-05, 1.9' -> (sorted [(date, creatinine)], [bad lines])."""
    from datetime import date
    readings, bad = [], []
    for line in text.splitlines():
        if not line.strip(): continue
        try:
            d, v = [x.strip() for x in line.split(",")]
            value = float(v)
            if value <= 0: raise ValueError
            readings.append((date.fromisoformat(d), value))
        except ValueError:
            bad.append(line.strip())
    return sorted(readings), bad

def latest_reading(readings, on_date):
    ok = [r for r in readings if r[0] <= on_date]
    return ok[-1] if ok else None

# ---------- 2. PARSING WITH DURATION ----------
UNIT_DAYS = {"d": 1, "day": 1, "days": 1, "w": 7, "wk": 7, "week": 7, "weeks": 7, "m": 30, "month": 30, "months": 30}
DUR1 = re.compile(r"\b(?:x|for)\s*(\d+)\s*(days?|d|weeks?|wk|w|months?|m)?\b", re.I)
DUR2 = re.compile(r"\b(\d+)\s*(days?|weeks?|months?)\b", re.I)

def parse_duration(line):
    """'Tab Combiflame TDS x 5d' -> ('Tab Combiflame TDS', 5). No duration -> None (ongoing)."""
    for rx in (DUR1, DUR2):
        m = rx.search(line)
        if m:
            unit = (m.group(2) or "d").lower()
            return (line[:m.start()] + " " + line[m.end():]).strip(), int(m.group(1)) * UNIT_DAYS[unit]
    return line, None

def parse_rx_line(line):
    clean, days = parse_duration(line)
    p = parse_line(clean)
    if not p: return None
    p["raw"] = line.strip()
    p["days"] = days
    return p

# ---------- 3. RESOLVING MEDICINES: verified / generic / proposed / unverified ----------
NUM = re.compile(r"\d+(?:\.\d+)?")

def known_ingredients():
    return {i for b in BRANDS.values() for i in b["ing"] if " " not in i}

def _result(status, label, ings, conf, note, sugg=None):
    if ings and label not in BRANDS:
        BRANDS[label] = {"aliases": [], "ing": dict(ings)}        # temporary entry so analyse() can use it
    return {"status": status, "label": label, "brand_key": label if ings else None,
            "ingredients": dict(ings), "confidence": round(conf, 2), "note": note, "suggestions": sugg or []}

def _num(x):
    v = float(x); return int(v) if v == int(v) else v

def resolve_medicine(name):
    """Returns a dict with status: verified | generic | proposed | unverified, plus ingredients and confidence."""
    key = name.lower().strip()
    if key in ALIAS_TO_BRAND:                                     # exact known spelling
        b = ALIAS_TO_BRAND[key]
        return _result("verified", b, BRANDS[b]["ing"], 1.0, "")
    typed_nums = NUM.findall(name)
    for w in re.findall(r"[a-z]+", key):                          # generic (chemical) name typed?
        for ing in known_ingredients():
            if SequenceMatcher(None, w, ing).ratio() >= 0.88:
                if typed_nums:
                    mg = _num(typed_nums[0])
                    return _result("generic", f"{ing.title()} {mg:g} mg (generic)", {ing: mg}, 0.9,
                                   "Generic name recognised; strength taken from the typed text.")
                return _result("unverified", name, {}, 0.0, "Generic name recognised but no strength was typed.")
    b, score, st, sugg = match_brand(name)
    if st == "unknown":
        return _result("unverified", name, {}, 0.0, "Not in our database. No safety checks were done for it.", sugg)
    ings = BRANDS[b]["ing"]
    brand_nums = NUM.findall(b)
    if typed_nums and brand_nums and set(typed_nums) != set(brand_nums):     # e.g. 'Dolo 500' vs 'Dolo 650'
        if len(ings) == 1:
            only = next(iter(ings)); mg = _num(typed_nums[0])
            return _result("proposed", f"{b} variant: {only} {mg:g} mg", {only: mg}, score * 0.9,
                           f"Typed strength ({typed_nums[0]}) differs from {b}. Strength taken from the typed text; this variant is not in our database.", sugg)
        return _result("proposed", b, ings, score * 0.8,
                       f"Typed strength ({typed_nums[0]}) differs from {b} in our database: dose uncertain.", sugg)
    if st == "ok":
        return _result("verified", b, ings, score, "")
    return _result("proposed", b, ings, score, f"Closest brand in our database is {b}; not verified.", sugg)

def make_course(doctor, rx_date, line):
    p = parse_rx_line(line)
    if not p: return None
    r = resolve_medicine(p["name"])
    end = rx_date + timedelta(days=p["days"] - 1) if p["days"] else None
    return {"doctor": doctor, "raw": p["raw"], "name": p["name"], "freq": p["freq"], "days": p["days"],
            "start": rx_date, "end": end, **r}

# ---------- 4. THE TIMELINE CHECK ----------
def _doctors_with(active, ing):
    return sorted({c["doctor"] for c in active if ing in c["ingredients"]})

def _segment_alerts(active, s, patient, readings):
    out = []
    items = [{"brand": c["brand_key"], "freq": c["freq"]} for c in active if c["ingredients"]]
    reading = latest_reading(readings, s)
    crcl = creatinine_clearance(patient["age"], patient["weight"], reading[1], patient["female"]) if reading else None
    box = bool(patient.get("kidney_box")) and reading is None
    totals = {}
    if items:
        _, alerts, totals = analyse(items, patient["age"], patient["weight"], patient["risk"], box)
        for sev, title, detail in alerts:
            if title.startswith("Duplicate ingredient: "):
                ing = title.split(": ", 1)[1]
                docs = _doctors_with(active, ing)
                if len(docs) > 1:
                    title = f"Cross-doctor duplicate: {ing}"
                    detail += f" Prescribed by {' and '.join(docs)}."
            elif title.startswith("Interaction: "):
                a, b = title.split(": ", 1)[1].split(" + ")
                da, db = _doctors_with(active, a), _doctors_with(active, b)
                if da and db and not set(da) & set(db):
                    detail += f" {a} from {', '.join(da)}; {b} from {', '.join(db)}: different doctors, so neither may have seen both."
            elif title.startswith("Two ") and " belong" in detail:
                names = detail.split(" belong")[0].split(" + ")
                by_doc = {n: _doctors_with(active, n) for n in names}
                if len(set().union(*[set(v) for v in by_doc.values()])) > 1:
                    detail += " From different doctors: " + "; ".join(f"{n} ({', '.join(v)})" for n, v in by_doc.items()) + "."
            out.append((sev, title, detail))
    if crcl is not None:                                           # kidney re-check
        for ing in totals:
            for below, sev, msg in RENAL_RULES.get(ing, []):
                if crcl < below:
                    out.append((sev, f"Kidney function: {ing}", f"{msg} (CrCl {crcl:.0f} mL/min from creatinine {reading[1]:g} on {reading[0].isoformat()})."))
                    break
    for c in active:                                               # unverified brands
        if c["status"] == "unverified":
            out.append(("MAJOR", f"Unverified medicine: {c['name']}",
                        f"Prescribed by {c['doctor']}. {c['note']} Ask a pharmacist."))
        elif c["status"] == "proposed":
            out.append(("MODERATE", f"Unverified composition: {c['name']}",
                        f"Proposed: {c['label']} ({c['confidence']*100:.0f}% match confidence, not a probability). {c['note']}"))
        if c["status"] != "unverified" and not c["freq"]:
            out.append(("MAJOR", f"Frequency missing: {c['name']}", "Daily dose could not be checked."))
    return out, totals, crcl

def merge_ranges(ranges):
    """Join touching or overlapping (start, end) ranges; end None means ongoing."""
    out = []
    for s_, e_ in sorted(ranges, key=lambda r: r[0]):
        if out and (out[-1][1] is None or out[-1][1] + timedelta(days=1) >= s_):
            if out[-1][1] is not None and (e_ is None or e_ > out[-1][1]):
                out[-1] = (out[-1][0], e_)
        else:
            out.append((s_, e_))
    return out

def check_timeline(courses, patient, readings):
    points = set()
    for c in courses:
        points.add(c["start"])
        if c["end"]: points.add(c["end"] + timedelta(days=1))
    for d, _ in readings: points.add(d)
    points = sorted(points)
    seen, segments = {}, []                 # title -> list of (start, end, severity, detail)
    for i, s in enumerate(points):
        e = points[i + 1] - timedelta(days=1) if i + 1 < len(points) else None
        active = [c for c in courses if c["start"] <= s and (c["end"] is None or c["end"] >= s)]
        if not active: continue
        alerts, totals, crcl = _segment_alerts(active, s, patient, readings)
        segments.append({"start": s, "end": e, "active": [c["label"] for c in active], "totals": totals, "crcl": crcl})
        for sev, title, detail in alerts:
            seen.setdefault(title, []).append((s, e, sev, detail))
    ranked = []
    for title, occ in seen.items():
        top = min(SEV_ORDER[o[2]] for o in occ)
        peak = [o for o in occ if SEV_ORDER[o[2]] == top]
        ranked.append({"severity": peak[0][2], "title": title, "detail": peak[0][3],
                       "ranges": merge_ranges([(o[0], o[1]) for o in occ]),
                       "peak_ranges": merge_ranges([(o[0], o[1]) for o in peak]),
                       "escalated": len(peak) < len(occ)})
    ranked.sort(key=lambda a: (SEV_ORDER[a["severity"]], a["peak_ranges"][0][0], a["title"]))
    for rank, a in enumerate(ranked, 1): a["rank"] = rank
    incomplete = any(c["status"] == "unverified" or not c["freq"] for c in courses)
    assumed = any(c["status"] in ("proposed", "generic") for c in courses)
    status = "INCOMPLETE" if incomplete else ("ASSUMPTIONS" if assumed else "CHECKED")
    return {"alerts": ranked, "segments": segments, "courses": courses, "status": status}

def recheck_with_new_value(courses, patient, readings):
    """Re-run the whole history with and without the newest kidney value; return what changed."""
    readings = sorted(readings)
    after = check_timeline(courses, patient, readings)
    before = check_timeline(courses, patient, readings[:-1])
    old = {(a["severity"], a["title"]) for a in before["alerts"]}
    new = [a for a in after["alerts"] if (a["severity"], a["title"]) not in old]
    return after, before, new

def date_text(r):
    s, e = r
    return f"{s.isoformat()} to {e.isoformat() if e else 'ongoing'}"

def timeline_grid(courses, max_days=28):
    from datetime import timedelta as td
    first = min(c["start"] for c in courses)
    ends = [c["end"] for c in courses if c["end"]] or [first]
    last = max(max(ends), max(c["start"] for c in courses) + td(days=6))
    last = min(last, first + td(days=max_days - 1))
    days = [first + td(days=i) for i in range((last - first).days + 1)]
    rows = []
    for c in courses:
        row = {"Doctor / medicine": f"{c['doctor']}: {c['name']} {c['freq'] or '?'}"}
        for d in days:
            on = c["start"] <= d and (c["end"] is None or c["end"] >= d)
            row[d.strftime("%d-%b")] = "#" if on else ""
        rows.append(row)
    return rows
