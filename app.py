import html
import streamlit as st
from datetime import date
from phase2 import (make_course, check_timeline, recheck_with_new_value, parse_kidney_readings,
                    timeline_grid, date_text, creatinine_clearance)

st.set_page_config(page_title="Prescription Safety Checker - Phase 2", page_icon="💊", layout="wide")

# =====================================================================
# THEME: gradients everywhere
# =====================================================================
THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');

:root {
  --g-brand: linear-gradient(120deg, #4f46e5 0%, #7c3aed 45%, #06b6d4 100%);
  --g-brand-soft: linear-gradient(135deg, #eef2ff 0%, #f5f3ff 45%, #ecfeff 100%);
  --g-side: linear-gradient(180deg, #1e1b4b 0%, #312e81 45%, #0e7490 100%);
  --g-ok: linear-gradient(120deg, #059669 0%, #10b981 55%, #34d399 100%);
  --g-warn: linear-gradient(120deg, #d97706 0%, #f59e0b 55%, #fbbf24 100%);
  --g-crit: linear-gradient(120deg, #be123c 0%, #e11d48 50%, #fb7185 100%);
  --g-major: linear-gradient(120deg, #c2410c 0%, #ea580c 50%, #fb923c 100%);
  --g-info: linear-gradient(120deg, #0369a1 0%, #0ea5e9 55%, #67e8f9 100%);
}

html, body, [class*="css"], .stApp { font-family: 'Poppins', sans-serif; }

/* page background */
.stApp { background: var(--g-brand-soft); background-attachment: fixed; }
[data-testid="stHeader"] { background: transparent; }

/* hero banner */
.hero {
  background: var(--g-brand);
  background-size: 200% 200%;
  animation: shift 12s ease infinite;
  border-radius: 20px;
  padding: 28px 34px;
  color: #fff;
  box-shadow: 0 14px 34px rgba(79, 70, 229, .35);
  margin-bottom: 18px;
}
.hero h1 { margin: 0; font-size: 2rem; font-weight: 700; color: #fff; letter-spacing: .2px; }
.hero p  { margin: 6px 0 0; opacity: .92; font-size: .95rem; color: #fff; }
@keyframes shift { 0% {background-position: 0% 50%;} 50% {background-position: 100% 50%;} 100% {background-position: 0% 50%;} }

/* section headings with gradient text + underline */
h2, h3, [data-testid="stSubheader"] {
  background: linear-gradient(90deg, #4338ca, #7c3aed 55%, #0891b2);
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent; color: transparent;
  font-weight: 700 !important;
}

/* sidebar */
[data-testid="stSidebar"] { background: var(--g-side); }
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
  background: linear-gradient(90deg, #a5f3fc, #e9d5ff);
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent;
}
[data-testid="stSidebar"] label, [data-testid="stSidebar"] p,
[data-testid="stSidebar"] span, [data-testid="stSidebar"] small,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: #e0e7ff !important; }
[data-testid="stSidebar"] input, [data-testid="stSidebar"] textarea { color: #1e1b4b !important; }

/* inputs */
div[data-baseweb="input"], div[data-baseweb="textarea"], div[data-baseweb="select"] > div {
  border-radius: 12px !important;
}
div[data-baseweb="input"]:focus-within, div[data-baseweb="textarea"]:focus-within {
  box-shadow: 0 0 0 2px #7c3aed55 !important;
}

/* doctor cards */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: linear-gradient(160deg, #ffffff 0%, #f5f3ff 100%);
  border: 1px solid #ddd6fe !important;
  border-top: 5px solid transparent !important;
  border-image: linear-gradient(90deg, #4f46e5, #7c3aed, #06b6d4) 1 !important;
  border-radius: 16px !important;
  box-shadow: 0 8px 22px rgba(99, 102, 241, .12);
}

/* buttons */
.stButton > button {
  background: var(--g-brand);
  background-size: 200% 200%;
  color: #fff; border: none; border-radius: 14px;
  padding: .7rem 1.8rem; font-weight: 600; font-size: 1rem;
  box-shadow: 0 8px 20px rgba(124, 58, 237, .35);
  transition: transform .15s ease, box-shadow .15s ease, background-position .4s ease;
}
.stButton > button:hover {
  background-position: 100% 50%;
  transform: translateY(-2px);
  box-shadow: 0 12px 26px rgba(124, 58, 237, .45);
  color: #fff;
}
.stButton > button:active { transform: translateY(0); }

/* status banners */
.banner {
  border-radius: 16px; padding: 16px 22px; color: #fff; font-weight: 500;
  box-shadow: 0 10px 24px rgba(0,0,0,.14); margin: 8px 0 14px;
}
.banner.ok   { background: var(--g-ok); }
.banner.warn { background: var(--g-warn); color: #3b2300; }
.banner.bad  { background: var(--g-crit); }
.banner.info { background: var(--g-info); }

/* alert cards */
.alert-card {
  border-radius: 16px; padding: 0; margin: 12px 0; overflow: hidden;
  background: #fff; box-shadow: 0 8px 22px rgba(15, 23, 42, .10);
}
.alert-head { padding: 12px 20px; color: #fff; font-weight: 600; display: flex; gap: 10px; align-items: center; }
.alert-head .pill {
  background: rgba(255,255,255,.25); border-radius: 999px; padding: 2px 12px;
  font-size: .72rem; letter-spacing: .6px; text-transform: uppercase;
}
.alert-body { padding: 14px 20px 16px; color: #1f2937; font-size: .93rem; line-height: 1.55; }
.alert-body .dates { margin-top: 8px; font-size: .84rem; color: #4b5563; }
.alert-body .peak  { margin-top: 4px; font-size: .84rem; font-weight: 600; color: #be123c; }
.sev-CRITICAL .alert-head { background: var(--g-crit); }
.sev-MAJOR    .alert-head { background: var(--g-major); }
.sev-MODERATE .alert-head, .sev-MINOR .alert-head, .sev-INFO .alert-head { background: var(--g-info); }
.sev-CRITICAL { border-left: 6px solid #e11d48; }
.sev-MAJOR    { border-left: 6px solid #ea580c; }

/* kidney tiles */
.tile {
  background: linear-gradient(135deg, #0f766e 0%, #0891b2 55%, #6366f1 100%);
  color: #fff; border-radius: 16px; padding: 16px 22px;
  box-shadow: 0 10px 24px rgba(8, 145, 178, .30);
}
.tile b { font-size: 1.15rem; }

/* tables / dataframes */
[data-testid="stTable"] table { border-radius: 14px; overflow: hidden; border-collapse: separate; border-spacing: 0; }
[data-testid="stTable"] thead tr th {
  background: linear-gradient(90deg, #4f46e5, #7c3aed); color: #fff !important; font-weight: 600;
}
[data-testid="stTable"] tbody tr:nth-child(even) td { background: #f5f3ff; }
[data-testid="stTable"] tbody tr:nth-child(odd) td  { background: #ffffff; }
[data-testid="stDataFrame"] { border-radius: 14px; overflow: hidden; box-shadow: 0 8px 22px rgba(99,102,241,.12); }

/* expanders */
[data-testid="stExpander"] {
  border: 1px solid #ddd6fe; border-radius: 14px; overflow: hidden;
  background: linear-gradient(160deg, #ffffff, #f5f3ff);
}
[data-testid="stExpander"] summary { background: linear-gradient(90deg, #ede9fe, #cffafe); font-weight: 600; }

/* thin gradient divider */
.divider { height: 4px; border-radius: 4px; background: var(--g-brand); margin: 22px 0 8px; opacity: .85; }
</style>
"""
st.markdown(THEME_CSS, unsafe_allow_html=True)


def esc(x):
    return html.escape(str(x))


def banner(kind, text):
    st.markdown(f'<div class="banner {kind}">{esc(text)}</div>', unsafe_allow_html=True)


def alert_card(a, dates, note=""):
    sev = esc(a["severity"])
    detail = esc(a["detail"]).replace("\n", "<br>")
    peak_html = f'<div class="peak">At this severity: {esc(note)}</div>' if note else ""
    st.markdown(
        f'<div class="alert-card sev-{sev}">'
        f'<div class="alert-head"><span class="pill">{sev}</span>#{esc(a["rank"])} {esc(a["title"])}</div>'
        f'<div class="alert-body">{detail}<div class="dates">Dates: {esc(dates)}</div>{peak_html}</div>'
        f'</div>', unsafe_allow_html=True)


# =====================================================================
# HEADER
# =====================================================================
st.markdown(
    '<div class="hero"><h1>💊 Prescription Safety Checker</h1>'
    '<p>Whole-history view &nbsp;·&nbsp; Prototype decision-support tool. '
    'Not a substitute for a doctor or pharmacist.</p></div>',
    unsafe_allow_html=True)

# ---------- patient and kidney values ----------
with st.sidebar:
    st.header("🧑‍⚕️ Patient")
    age = st.number_input("Age (years)", 0, 110, 68)
    weight = st.number_input("Weight (kg)", 1.0, 200.0, 58.0)
    female = st.selectbox("Sex", ["Male", "Female"]) == "Female"
    risk = st.checkbox("Liver disease / regular alcohol")
    kidney_box = st.checkbox("Kidney disease (used only if no creatinine values below)")
    st.header("🩺 Kidney function")
    kidney_text = st.text_area("One reading per line: YYYY-MM-DD, serum creatinine (mg/dL)",
                               "2026-10-01, 1.0\n2026-10-06, 2.1", height=110)
    st.caption("When a new report arrives, add a new line. Everything is re-checked.")

patient = {"age": age, "weight": weight, "female": female, "risk": risk, "kidney_box": kidney_box}
readings, bad_lines = parse_kidney_readings(kidney_text)
if bad_lines:
    st.sidebar.error("Could not read these kidney lines: " + "; ".join(bad_lines))

# ---------- three doctors ----------
DEFAULTS = [
    ("Dr A (physician)", date(2026, 10, 1), "Tab Combiflame 1 TDS x 5d\nTab Glycomet 500 BD"),
    ("Dr B (orthopaedic)", date(2026, 10, 3), "Tab Voveran 50 BD x 5d\nTab Dolo 650 TDS x 5d"),
    ("Dr C (cardiologist)", date(2026, 10, 4), "Tab Ecosprin 75 OD\nTab Telma 40 OD\nTab Pan D OD x 10d"),
]
st.write("One medicine per line: name, frequency, and optionally a duration (for example `x 5d`, `for 2 weeks`). "
         "No duration means the medicine is treated as ongoing.")
columns = st.columns(3)
inputs = []
for i, (col, (dname, ddate, dtext)) in enumerate(zip(columns, DEFAULTS)):
    with col:
        with st.container(border=True):
            name = st.text_input("Doctor", dname, key=f"name{i}")
            when = st.date_input("Prescription date", ddate, key=f"date{i}")
            text = st.text_area("Prescription", dtext, height=150, key=f"text{i}")
        inputs.append((name, when, text))

if st.button("🔍 Check whole history"):
    st.session_state["run2"] = True

if st.session_state.get("run2"):
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    courses = []
    for name, when, text in inputs:
        for line in [l for l in text.splitlines() if l.strip()]:
            c = make_course(name, when, line)
            if c: courses.append(c)
    if not courses:
        banner("info", "No medicines found.")
    else:
        after, before, new = recheck_with_new_value(courses, patient, readings) if readings else (
            check_timeline(courses, patient, readings), None, [])

        # --- overall status (never a plain green tick when something was not checked) ---
        if after["status"] == "INCOMPLETE":
            banner("bad", "⛔ INCOMPLETE CHECK: at least one medicine could not be verified or has no frequency. "
                          "Results below do not cover it.")
        elif after["status"] == "ASSUMPTIONS":
            banner("warn", "⚠️ CHECKED WITH ASSUMPTIONS: some compositions were proposed or taken from generic names. "
                           "See the notes.")
        else:
            banner("ok", "✅ All medicines were identified and checked against our database.")

        # --- timeline ---
        st.subheader("📅 Merged timeline")
        st.dataframe(timeline_grid(courses))

        # --- medicines table with confidence ---
        st.subheader("💊 Medicines identified")
        st.table([{"Doctor": c["doctor"], "Typed": c["name"], "Frequency": c["freq"] or "?",
                   "Start": c["start"].isoformat(), "End": c["end"].isoformat() if c["end"] else "ongoing",
                   "Identified as": c["label"] if c["ingredients"] else "UNVERIFIED",
                   "Status": c["status"], "Confidence": f"{c['confidence']*100:.0f}%" if c["ingredients"] else "-",
                   "Ingredients": ", ".join(f"{k} {v:g} mg" for k, v in c["ingredients"].items())} for c in courses])

        # --- ranked alerts ---
        alerts = after["alerts"]
        st.subheader("🚨 Alerts, most urgent first")
        main = [a for a in alerts if a["severity"] in ("CRITICAL", "MAJOR")]
        rest = [a for a in alerts if a["severity"] not in ("CRITICAL", "MAJOR")]
        if not main:
            banner("ok", "No critical or major alerts.")
        for a in main:
            dates = " ; ".join(date_text(r) for r in a["ranges"])
            peak = " ; ".join(date_text(r) for r in a["peak_ranges"]) if a["escalated"] else ""
            alert_card(a, dates, peak)
        if rest:
            with st.expander(f"{len(rest)} more notes"):
                for a in rest:
                    alert_card(a, " ; ".join(date_text(r) for r in a["ranges"]))

        # --- kidney re-check ---
        if len(readings) >= 1:
            st.subheader("🩺 Kidney re-check")
            latest = readings[-1]
            crcl = creatinine_clearance(age, weight, latest[1], female)
            st.markdown(
                f'<div class="tile">Latest value: creatinine <b>{latest[1]:g} mg/dL</b> on '
                f'{esc(latest[0].isoformat())}, estimated clearance about <b>{crcl:.0f} mL/min</b>.</div>',
                unsafe_allow_html=True)
            if before is not None and len(readings) > 1:
                if new:
                    banner("warn", "New alerts caused by the latest kidney value: "
                           + "; ".join(f"[{a['severity']}] {a['title']}" for a in new))
                else:
                    banner("ok", "The latest kidney value did not create any new alerts.")

        # --- period-by-period details ---
        with st.expander("Day-range details (what was active and the daily totals)"):
            for s in after["segments"]:
                end = s["end"].isoformat() if s["end"] else "ongoing"
                clr = f", CrCl about {s['crcl']:.0f} mL/min" if s["crcl"] is not None else ""
                st.write(f"**{s['start'].isoformat()} to {end}**{clr}: " + ", ".join(s["active"]))
                st.write({k: round(v, 1) for k, v in s["totals"].items()})
