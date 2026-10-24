"""Prescription Safety Checker - engine (MVP). ALL medical data below is ILLUSTRATIVE:
have a pharmacist verify every row before you present it."""
from difflib import SequenceMatcher
from itertools import combinations

# ---------- 1. DATA (grow this list as time allows) ----------
BRANDS = {
    "Dolo 650":        {"aliases": ["dolo 650", "dolo"],            "ing": {"paracetamol": 650}},
    "Crocin 500":      {"aliases": ["crocin 500", "crocin"],        "ing": {"paracetamol": 500}},
    "Combiflam":       {"aliases": ["combiflam"],                   "ing": {"ibuprofen": 400, "paracetamol": 325}},
    "Brufen 400":      {"aliases": ["brufen 400", "brufen"],        "ing": {"ibuprofen": 400}},
    "Voveran 50":      {"aliases": ["voveran 50", "voveran"],       "ing": {"diclofenac": 50}},
    "Zerodol-P":       {"aliases": ["zerodol-p", "zerodol p"],      "ing": {"aceclofenac": 100, "paracetamol": 325}},
    "Ecosprin 75":     {"aliases": ["ecosprin 75", "ecosprin"],     "ing": {"aspirin": 75}},
    "Pan 40":          {"aliases": ["pan 40", "pan"],               "ing": {"pantoprazole": 40}},
    "Augmentin 625":   {"aliases": ["augmentin 625", "augmentin"],  "ing": {"amoxicillin": 500, "clavulanic acid": 125}},
    "Azithral 500":    {"aliases": ["azithral 500", "azithral"],    "ing": {"azithromycin": 500}},
    "Cetzine":         {"aliases": ["cetzine", "cetrizine"],        "ing": {"cetirizine": 10}},
    "Glycomet 500":    {"aliases": ["glycomet 500", "glycomet"],    "ing": {"metformin": 500}},
    "Telma 40":        {"aliases": ["telma 40", "telma"],           "ing": {"telmisartan": 40}},
    "Telma-H":         {"aliases": ["telma-h", "telma h"],          "ing": {"telmisartan": 40, "hydrochlorothiazide": 12.5}},
    "Atorva 10":       {"aliases": ["atorva 10", "atorva"],         "ing": {"atorvastatin": 10}},
    "Warfarin 5":      {"aliases": ["warfarin 5", "warfarin", "warf"], "ing": {"warfarin": 5}},
    "Clarithromycin 500": {"aliases": ["clarithromycin 500", "claribid"], "ing": {"clarithromycin": 500}},
}

CLASSES = {  # ingredient -> drug class
    "ibuprofen": "NSAID", "diclofenac": "NSAID", "aceclofenac": "NSAID", "aspirin": "NSAID",
    "telmisartan": "ARB", "warfarin": "anticoagulant", "atorvastatin": "statin",
    "clarithromycin": "macrolide", "pantoprazole": "PPI", "cetirizine": "antihistamine",
}

# daily limits in mg: (normal adult, adult with risk factor)  -> pharmacist to confirm
LIMITS = {
    "paracetamol": (4000, 3000),
    "ibuprofen":   (1200, 1200),
    "diclofenac":  (150, 150),
    "metformin":   (2000, 2000),
}

# specific pair rules: (ingredient or class, ingredient or class, severity, message)
PAIR_RULES = [
    ("NSAID", "anticoagulant", "CRITICAL", "NSAID with a blood thinner: high bleeding risk."),
    ("ibuprofen", "aspirin", "MAJOR", "Ibuprofen can block aspirin's heart protection and raises stomach-bleeding risk."),
    ("atorvastatin", "clarithromycin", "MAJOR", "Clarithromycin can raise statin levels: muscle damage risk."),
    ("ARB", "NSAID", "MODERATE", "NSAIDs can reduce the effect of ARBs and strain the kidneys."),
]

FREQ = {"od": 1, "qd": 1, "hs": 1, "bd": 2, "bid": 2, "tds": 3, "tid": 3, "qid": 4, "sos": 4}
SEV_ORDER = {"CRITICAL": 0, "MAJOR": 1, "MODERATE": 2, "INFO": 3}

# ---------- 2. PARSING ----------
def doses_per_day(code):
    code = code.lower()
    if code in FREQ: return FREQ[code]
    parts = code.split("-")              # 1-0-1 style
    if all(p.isdigit() for p in parts) and len(parts) >= 3: return sum(int(p) for p in parts)
    return None

def parse_line(line):
    words = line.replace(".", " ").split()
    words = [w for w in words if w.lower() not in ("tab", "cap", "syp", "t", "c")]
    if not words: return None
    words = [w for w in words if not (w.isdigit() and len(w) == 1)]   # drop quantity like '1'
    freq = None
    for i in range(len(words) - 1, -1, -1):     # find frequency code from the end
        if doses_per_day(words[i]) is not None:
            freq = words.pop(i); break
    return {"raw": line.strip(), "name": " ".join(words), "freq": freq}

# ---------- 3. BRAND MATCHING ----------
ALIAS_TO_BRAND = {a: b for b, d in BRANDS.items() for a in d["aliases"]}

def match_brand(name):
    name = name.lower().strip()
    scored = sorted(((SequenceMatcher(None, name, a).ratio(), a) for a in ALIAS_TO_BRAND), reverse=True)
    best_score, best_alias = scored[0]
    suggestions = []
    for _, a in scored[:5]:
        if ALIAS_TO_BRAND[a] not in suggestions: suggestions.append(ALIAS_TO_BRAND[a])
    status = "ok" if best_score >= 0.85 else "confirm" if best_score >= 0.6 else "unknown"
    return ALIAS_TO_BRAND[best_alias], best_score, status, suggestions[:3]

# ---------- 4. ANALYSIS ----------
def analyse(items, age=30, weight=60, risk_factor=False, kidney_disease=False):
    """items: list of {'brand': 'Combiflam', 'freq': 'TDS'}  -> (table, alerts)"""
    totals, owners, table, alerts = {}, {}, [], []
    for it in items:
        brand = BRANDS[it["brand"]]
        n = doses_per_day(it["freq"]) if it.get("freq") else None
        if n is None:
            alerts.append(("INFO", f"Frequency missing for {it['brand']}", "Cannot add its daily dose; please enter OD/BD/TDS..."))
            n = 0
        if (it.get("freq") or "").lower() == "sos":
            alerts.append(("INFO", f"{it['brand']} is SOS", "Worst case of 4 doses/day assumed for the dose check."))
        table.append({"Medicine": it["brand"], "Frequency": it.get("freq") or "?", "Doses/day": n,
                      "Ingredients": ", ".join(f"{k} {v:g} mg" for k, v in brand["ing"].items())})
        for ing, mg in brand["ing"].items():
            totals[ing] = totals.get(ing, 0) + mg * n
            owners.setdefault(ing, []).append(it["brand"])

    # duplicates: same ingredient in 2+ different line items
    for ing, who in owners.items():
        if len(who) > 1:
            alerts.append(("MAJOR", f"Duplicate ingredient: {ing}",
                           f"{ing.title()} is in {', '.join(who)}. Combined: {totals[ing]:g} mg/day."))
    # duplicate classes (two different NSAIDs etc.)
    by_class = {}
    for ing in totals:
        c = CLASSES.get(ing)
        if c in ("NSAID", "statin", "PPI", "antihistamine"): by_class.setdefault(c, []).append(ing)
    for c, ings in by_class.items():
        if len(ings) > 1 and not {"ibuprofen", "aspirin"} >= set(ings):   # ibuprofen+aspirin has own rule
            alerts.append(("MAJOR", f"Two {c}s together", f"{' + '.join(ings)} belong to the same class."))

    # interactions
    for a, b in combinations(sorted(totals), 2):
        tags_a, tags_b = {a, CLASSES.get(a)}, {b, CLASSES.get(b)}
        for x, y, sev, msg in PAIR_RULES:
            if (x in tags_a and y in tags_b) or (y in tags_a and x in tags_b):
                alerts.append((sev, f"Interaction: {a} + {b}", msg)); break

    # dose limits (patient-specific)
    for ing, (normal, risky) in LIMITS.items():
        if ing not in totals: continue
        limit = risky if (risk_factor or age >= 65) else normal
        if ing == "paracetamol" and age < 12 and weight:
            limit = 60 * weight                         # 60 mg/kg/day for children
        if totals[ing] > limit:
            alerts.append(("CRITICAL", f"{ing.title()} over daily limit",
                           f"{totals[ing]:g} mg/day vs limit {limit:g} mg/day for this patient."))
        elif totals[ing] > 0.8 * limit:
            alerts.append(("MODERATE", f"{ing.title()} close to limit", f"{totals[ing]:g} of {limit:g} mg/day."))
    if kidney_disease and any(CLASSES.get(i) == "NSAID" for i in totals):
        alerts.append(("MAJOR", "NSAID with kidney disease", "NSAIDs can worsen kidney function; review with prescriber."))
    if kidney_disease and "metformin" in totals:
        alerts.append(("MAJOR", "Metformin with kidney disease", "Dose may need adjustment; review with prescriber."))

    alerts.sort(key=lambda a: SEV_ORDER[a[0]])
    return table, alerts, totals
