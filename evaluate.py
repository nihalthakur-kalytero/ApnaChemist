"""Run: py -3.13 evaluate_phase2.py   -> checks the Phase 2 features and prints PASS/FAIL for each."""
from datetime import date
from phase2 import (make_course, check_timeline, recheck_with_new_value, parse_duration,
                    parse_kidney_readings, resolve_medicine)

ADULT = {"age": 40, "weight": 70, "female": False, "risk": False, "kidney_box": False}
ELDER = {"age": 68, "weight": 58, "female": False, "risk": False, "kidney_box": False}
D = date

def build(rx):
    """rx: list of (doctor, date, [lines])"""
    return [make_course(doc, d, line) for doc, d, lines in rx for line in lines]

def titles(res, sev=None):
    return [a["title"] for a in res["alerts"] if sev is None or a["severity"] == sev]

results = []
def check(name, ok):
    results.append(ok); print(("PASS  " if ok else "FAIL  ") + name)

# 1. cross-doctor duplicate, only while the courses overlap
res = check_timeline(build([("Dr A", D(2026,10,1), ["Tab Combiflame 1 TDS x 5d"]),
                            ("Dr B", D(2026,10,3), ["Tab Dolo 650 TDS x 3d"])]), ADULT, [])
dup = [a for a in res["alerts"] if a["title"] == "Cross-doctor duplicate: paracetamol"]
check("Cross-doctor duplicate found", len(dup) == 1)
check("...and only on the overlapping days (3 to 5 Oct)", dup and dup[0]["ranges"] == [(D(2026,10,3), D(2026,10,5))])

# 2. no overlap -> no duplicate
res = check_timeline(build([("Dr A", D(2026,10,1), ["Tab Dolo 650 TDS x 3d"]),
                            ("Dr B", D(2026,10,4), ["Tab Combiflam TDS x 3d"])]), ADULT, [])
check("Back-to-back courses are NOT flagged as duplicates", not any("uplicate" in t for t in titles(res)))

# 3. same brand from two doctors
res = check_timeline(build([("Dr A", D(2026,10,1), ["Tab Dolo 650 TDS x 5d"]),
                            ("Dr B", D(2026,10,2), ["Tab Dolo 650 TDS x 5d"])]), ADULT, [])
check("Same brand from two doctors flagged", "Cross-doctor duplicate: paracetamol" in titles(res))

# 4. kidney re-check when a new value arrives
courses = build([("Dr A", D(2026,10,1), ["Tab Glycomet 500 BD", "Tab Voveran 50 BD x 5d"])])
readings, bad = parse_kidney_readings("2026-10-01, 1.0\n2026-10-06, 2.1")
after, before, new = recheck_with_new_value(courses, ELDER, readings)
check("Kidney values parsed", len(readings) == 2 and not bad)
check("Before the new value: no metformin kidney alert", "Kidney function: metformin" not in titles(before))
check("After the new value: metformin kidney alert is CRITICAL", "Kidney function: metformin" in titles(after, "CRITICAL"))
check("The re-check lists it as NEW", any(a["title"] == "Kidney function: metformin" for a in new))

# 5. unverified brand
res = check_timeline(build([("Dr A", D(2026,10,1), ["Tab Zzzz 1 OD", "Tab Pan 40 OD"])]), ADULT, [])
check("Unknown brand marked unverified (MAJOR)", "Unverified medicine: Zzzz" in titles(res, "MAJOR"))
check("Overall status is INCOMPLETE, not a green all-clear", res["status"] == "INCOMPLETE")

# 6. strength mismatch becomes a proposal, with the typed strength
r = resolve_medicine("Dolo 500")
check("Dolo 500 is proposed as paracetamol 500 mg (not 650)", r["status"] == "proposed" and r["ingredients"] == {"paracetamol": 500})
check("...with a confidence value below 1", 0 < r["confidence"] < 1)

# 7. generic name
r = resolve_medicine("Pantoprazole 40")
check("Generic name recognised with strength", r["status"] == "generic" and r["ingredients"] == {"pantoprazole": 40})
check("Generic name without a strength stays unverified", resolve_medicine("Pantoprazole")["status"] == "unverified")

# 8. ranking
res = check_timeline(build([("Dr A", D(2026,10,1), ["Tab Warfarin 5 OD", "Tab Voveran 50 BD x 5d"]),
                            ("Dr B", D(2026,10,1), ["Tab Dolo 650 TDS x 5d", "Tab Combiflam TDS x 5d"])]), ADULT, [])
order = {"CRITICAL": 0, "MAJOR": 1, "MODERATE": 2, "INFO": 3}
sev_list = [order[a["severity"]] for a in res["alerts"]]
check("Alerts are ranked most urgent first", sev_list == sorted(sev_list) and res["alerts"][0]["severity"] == "CRITICAL")
check("Ranks are numbered 1..n", [a["rank"] for a in res["alerts"]] == list(range(1, len(res["alerts"]) + 1)))

# 9. duration parsing
check("Duration 'x 5d'", parse_duration("Tab Dolo 650 TDS x 5d")[1] == 5)
check("Duration 'for 2 weeks'", parse_duration("Tab Pan 40 OD for 2 weeks")[1] == 14)
check("Duration '5 days'", parse_duration("Tab Pan 40 OD 5 days")[1] == 5)
check("Strength 40 is not mistaken for a duration", parse_duration("Tab Pan 40 OD")[1] is None)

# 10. missing frequency
res = check_timeline(build([("Dr A", D(2026,10,1), ["Tab Dolo 650"])]), ADULT, [])
check("Missing frequency -> INCOMPLETE", res["status"] == "INCOMPLETE")

# 11. a safe, clean history
res = check_timeline(build([("Dr A", D(2026,10,1), ["Tab Augmentin 625 BD x 5d"]),
                            ("Dr B", D(2026,10,1), ["Tab Pan 40 OD x 5d"])]), ADULT, parse_kidney_readings("2026-10-01, 0.9")[0])
check("Safe history: no Critical/Major alerts and status CHECKED",
      not titles(res, "CRITICAL") and not titles(res, "MAJOR") and res["status"] == "CHECKED")

print(f"\n{sum(results)}/{len(results)} checks passed")
