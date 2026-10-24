"""Prescription Safety Checker - Telegram bot (multi-doctor).
Keep this file in the same folder as engine.py.   Run:  python bot.py
Add prescriptions from several doctors, then check them ALL TOGETHER.
Decision support only. Medicine data in engine.py must be verified by a pharmacist."""
import os, re, logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup as Kb
from telegram.error import BadRequest
from telegram.ext import (Application, CommandHandler, MessageHandler,
                          CallbackQueryHandler, ContextTypes, filters)
from engine import parse_line, match_brand, analyse, doses_per_day, BRANDS, CLASSES

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
for noisy in ("httpx", "httpcore", "telegram", "apscheduler"):
    logging.getLogger(noisy).setLevel(logging.WARNING)      # also keeps the token out of the console


def Btn(text, data):
    """Button that sends `data` back to the bot when tapped (must be callback_data, not url)."""
    return InlineKeyboardButton(text, callback_data=data)


ICON = {"CRITICAL": "🔴", "MAJOR": "🟠", "MODERATE": "🟡", "INFO": "🔵"}
EXAMPLE_RXS = [("Dr Sharma", "Tab Combiflame 1 TDS\nTab Pan 40 OD"),
               ("Dr Mehta", "Tab Dolo 650 SOS\nTab Ecosprin 75 OD")]
WELCOME = ("💊 Prescription Safety Checker\n\n"
           "Patients often get prescriptions from more than one doctor. I check them ALL TOGETHER for:\n"
           "• the same medicine hidden in different brands\n"
           "• risky medicine combinations\n"
           "• daily doses that are too high\n\n"
           "Decision support only. I do not replace a doctor or pharmacist.\n\n"
           "Who is the patient?")
RX_HELP = ("Now send this doctor's medicines, one per line:\n\n"
           "Tab Combiflam 1 TDS\nTab Dolo 650 SOS\nTab Pan 40 OD\n\n"
           "Frequency can be OD, BD, TDS, QID, SOS or 1-0-1.\n"
           "Tip: you can leave out 'Tab'.")


# ---------- helpers ----------
def get_token():
    t = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not t and os.path.exists("token.txt"):
        t = open("token.txt").read().strip()
    if not t:
        t = input("Paste your Telegram bot token from @BotFather: ").strip()
        if input("Save it to token.txt so you are not asked again? (y/n): ").lower().startswith("y"):
            open("token.txt", "w").write(t)
    return t


async def send(ctx, chat, text, kb=None):
    """Send text; split very long messages so Telegram never rejects them."""
    chunks, cur = [], ""
    for part in text.split("\n\n"):
        if len(cur) + len(part) + 2 > 3500 and cur:
            chunks.append(cur); cur = part
        else:
            cur = f"{cur}\n\n{part}" if cur else part
    chunks.append(cur)
    for i, c in enumerate(chunks):
        await ctx.bot.send_message(chat, c[:4000], reply_markup=kb if i == len(chunks) - 1 else None)


async def safe_edit(q, text, kb=None):
    try:
        await q.edit_message_text(text, reply_markup=kb)
    except BadRequest:
        pass                                   # message too old or unchanged: not a real problem


def fmt(it):
    n = doses_per_day(it["freq"]) if it.get("freq") else None
    return f"{it['brand']} ({n}/day)" if n else f"{it['brand']} (no frequency)"


def patient_kb():
    return Kb([[Btn("🧑 Adult", "p:adult")],
               [Btn("👴 Elderly (65+)", "p:elder")],
               [Btn("🧒 Child (under 12)", "p:child")]])


def read_number(text):
    m = re.search(r"\d+(?:\.\d+)?", text)
    return float(m.group()) if m else None


# ---------- step 1: patient ----------
async def ask_patient(ctx, chat, intro=None):
    ctx.user_data.clear()
    ctx.user_data["state"] = "patient"
    await send(ctx, chat, intro or WELCOME, patient_kb())


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await ask_patient(ctx, update.effective_chat.id)


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await send(ctx, update.effective_chat.id,
               "How to use me:\n1. Choose the patient.\n2. Tick any health conditions.\n"
               "3. Add each doctor's prescription (type the doctor's name, then the medicines).\n"
               "4. Tap 'Add another doctor' as many times as needed.\n"
               "5. Tap 'Check all together'.\n\nCommands: /start begins again, /help shows this message.")


async def expired(ctx, chat):
    await ask_patient(ctx, chat, "That button is from an earlier session, so let's start again.\n\nWho is the patient?")


# ---------- step 2: child details ----------
async def child_age(ctx, chat, text):
    v = read_number(text)
    if v is not None and "month" in text.lower():
        v = v / 12
    if v is None or not (0 <= v < 12):
        await send(ctx, chat, "Please type the child's age as a number under 12, for example: 6\n"
                              "(For 12 or older, choose Adult.)", Kb([[Btn("⬅️ Back", "change")]]))
        return
    ctx.user_data["age"] = v
    ctx.user_data["age_text"] = text.strip()
    ctx.user_data["state"] = "child_weight"
    await send(ctx, chat, "⚖️ And the child's weight in kg? For example: 15")


async def child_weight(ctx, chat, text):
    v = read_number(text)
    if v is None or not (1 <= v <= 60):
        await send(ctx, chat, "Please type the weight in kg as a number between 1 and 60, for example: 15",
                   Kb([[Btn("⬅️ Back", "change")]]))
        return
    ud = ctx.user_data
    ud["weight"] = v
    ud["label"] = f"Child ({ud['age_text']}, {v:g} kg)"
    await ask_conditions(ctx, chat)


# ---------- step 3: conditions ----------
def cond_kb(ud):
    m = lambda on: "✅" if on else "⬜"
    return Kb([[Btn(f"{m(ud.get('risk'))} Liver disease / regular alcohol", "t:liver")],
               [Btn(f"{m(ud.get('kidney'))} Kidney disease", "t:kidney")],
               [Btn("Done ➡️", "t:done")]])


async def ask_conditions(ctx, chat):
    ud = ctx.user_data
    ud["risk"], ud["kidney"], ud["state"] = False, False, "conditions"
    await send(ctx, chat, "Does any of this apply to the patient?\nTap to select, then press Done.\n"
                          "(Tap Done right away if none apply.)", cond_kb(ud))


# ---------- step 4: one doctor's prescription at a time ----------
async def ask_doctor(ctx, chat):
    ud = ctx.user_data
    ud["state"] = "doctor"
    ud.setdefault("rxs", [])
    n = len(ud["rxs"]) + 1
    rows = [[Btn("⏭ Skip name", "skipdoc")]]
    if n == 1:
        rows.insert(0, [Btn("🧪 Try a 2-doctor example", "example")])
    await send(ctx, chat, f"👨‍⚕️ Prescription {n}: which doctor wrote it?\n"
                          "Type the doctor's name (for example: Dr Sharma), or skip.", Kb(rows))


async def got_doctor(ctx, chat, name):
    ud = ctx.user_data
    ud["cur_doc"] = (name or "").strip()[:30] or f"Doctor {len(ud['rxs']) + 1}"
    ud["state"] = "rx"
    await send(ctx, chat, f"👨‍⚕️ {ud['cur_doc']}\n\n{RX_HELP}")


def read_lines(text):
    """text -> (confident items, lines needing confirmation, unrecognised names)."""
    items, queue, unknown = [], [], []
    for line in [l for l in text.splitlines() if l.strip()]:
        p = parse_line(line)
        if not p or not p["name"].strip():
            continue
        brand, score, status, sugg = match_brand(p["name"])
        if status == "unknown":
            unknown.append(p["name"])
        elif status == "confirm":
            queue.append({"name": p["name"], "freq": p["freq"], "sugg": sugg})
        else:
            items.append({"brand": brand, "freq": p["freq"]})
    return items, queue, unknown


async def process_rx(ctx, chat, text):
    ud = ctx.user_data
    items, queue, unknown = read_lines(text)
    for u in unknown:
        await send(ctx, chat, f"❌ I don't recognise '{u}'. Check the spelling and add that medicine again.")
    if not items and not queue:
        await send(ctx, chat, "I couldn't identify any medicine in that. Please send this doctor's medicines again.")
        return
    ud["items"], ud["queue"] = items, queue
    await next_step(ctx, chat)


async def next_step(ctx, chat):
    ud = ctx.user_data
    if ud["queue"]:
        ud["state"] = "confirm"
        cur = ud["queue"][0]
        rows = [[Btn(s, f"pick:{i}")] for i, s in enumerate(cur["sugg"])]
        rows.append([Btn("None of these", "skip")])
        await send(ctx, chat, f"🤔 You typed '{cur['name']}'. Did you mean:", Kb(rows))
    else:
        await finish_rx(ctx, chat)


async def finish_rx(ctx, chat):
    ud = ctx.user_data
    if not ud.get("items"):
        ud["state"] = "rx"
        await send(ctx, chat, "No medicine was kept for this doctor. Please send the medicines again.")
        return
    ud["rxs"].append({"doctor": ud["cur_doc"], "items": ud["items"]})
    ud["items"] = []
    await show_review(ctx, chat, added=True)


def review_kb(ud):
    rows = [[Btn("➕ Add another doctor's prescription", "adddoc")],
            [Btn("✅ Check all together", "checkall")]]
    rows.append([Btn("↩️ Remove last prescription", "undo"), Btn("🔄 Change patient", "change")])
    return Kb(rows)


async def show_review(ctx, chat, added=False):
    ud = ctx.user_data
    ud["state"] = "review"
    rxs = ud["rxs"]
    lines = ["✅ Added." if added else "Prescriptions so far:"]
    for i, rx in enumerate(rxs, 1):
        lines.append(f"{i}. 👨‍⚕️ {rx['doctor']}: " + ", ".join(fmt(it) for it in rx["items"]))
    doctors = len({rx["doctor"] for rx in rxs})
    lines.append(f"{len(rxs)} prescription{'s' if len(rxs) > 1 else ''}, {doctors} doctor{'s' if doctors > 1 else ''}. "
                 "Does the patient have another doctor's prescription?")
    await send(ctx, chat, "\n\n".join(lines), review_kb(ud))


# ---------- the combined check ----------
def sources_for(alert, rxs):
    """Which (brand, doctor) pairs does this alert involve?"""
    text = (alert[1] + " " + alert[2]).lower()
    hit = set()
    for rx in rxs:
        for it in rx["items"]:
            for ing in BRANDS[it["brand"]]["ing"]:
                cls = (CLASSES.get(ing) or "").lower()
                if ing in text or (cls and re.search(rf"\b{re.escape(cls)}s?\b", text)):
                    hit.add((it["brand"], rx["doctor"]))
    return hit


def cross_note(alert, rxs):
    hit = sources_for(alert, rxs)
    if len({doc for _, doc in hit}) > 1:
        return "👥 Different doctors: " + " + ".join(f"{b} ({d})" for b, d in sorted(hit, key=lambda x: x[1]))
    return None


async def report(ctx, chat):
    ud = ctx.user_data
    rxs = ud.get("rxs") or []
    ud["state"] = "review"
    kb_rows = [[Btn("➕ Add another doctor's prescription", "adddoc")],
               [Btn("🆕 New check, same patient", "newcheck"), Btn("🔄 Change patient", "change")]]
    if not rxs:
        await send(ctx, chat, "There is no prescription to check yet.", Kb(kb_rows))
        return
    all_items = [dict(it, doctor=rx["doctor"]) for rx in rxs for it in rx["items"]]
    table, alerts, _ = analyse(all_items, ud["age"], ud["weight"], ud.get("risk", False), ud.get("kidney", False))
    main = [a for a in alerts if a[0] in ("CRITICAL", "MAJOR")]
    rest = [a for a in alerts if a[0] not in ("CRITICAL", "MAJOR")]
    multi = len({rx["doctor"] for rx in rxs}) > 1

    notes = [cross_note(a, rxs) if multi else None for a in main]
    if main:
        n = len(main)
        lines = [f"⚠️ {n} important issue{'s' if n > 1 else ''} found"]
        cross = sum(1 for x in notes if x)
        if cross:
            lines.append(f"👥 {cross} of these involve medicines from different doctors, "
                         "which is easy to miss when each doctor sees only their own prescription.")
        for a, note in zip(main, notes):
            lines.append(f"{ICON[a[0]]} {a[1]}\n{a[2]}" + (f"\n{note}" if note else ""))
        lines.append("👉 Please show this to the doctors or a pharmacist before the medicines are taken together.")
    else:
        lines = ["✅ No critical or major issues found in our database."]
    lines.append("💊 Checked together:\n" + "\n".join(
        f"👨‍⚕️ {rx['doctor']}: " + ", ".join(fmt(it) for it in rx["items"]) for rx in rxs))
    lines.append(f"🧾 Patient: {ud.get('label', '')}")
    lines.append("This is decision support only, not a diagnosis.")
    ud["rest"] = "\n\n".join(
        f"{ICON[s]} {t}: {d}" + (f"\n{cross_note((s, t, d), rxs)}" if multi and cross_note((s, t, d), rxs) else "")
        for s, t, d in rest)
    more = [[Btn(f"ℹ️ {len(rest)} more note{'s' if len(rest) > 1 else ''}", "more")]] if rest else []
    await send(ctx, chat, "\n\n".join(lines), Kb(more + kb_rows))


async def load_example(ctx, chat):
    ud = ctx.user_data
    ud["rxs"] = []
    for doc, text in EXAMPLE_RXS:
        items, queue, _ = read_lines(text)
        ud["rxs"].append({"doctor": doc, "items": items})
    await send(ctx, chat, "Loaded an example with two doctors:\n" + "\n".join(
        f"👨‍⚕️ {rx['doctor']}: " + ", ".join(fmt(it) for it in rx["items"]) for rx in ud["rxs"]))
    await report(ctx, chat)


# ---------- incoming text ----------
async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ud, chat, text = ctx.user_data, update.effective_chat.id, update.message.text or ""
    state = ud.get("state")
    if state == "child_age":
        await child_age(ctx, chat, text)
    elif state == "child_weight":
        await child_weight(ctx, chat, text)
    elif state == "doctor":
        await got_doctor(ctx, chat, text)
    elif state == "rx":
        await process_rx(ctx, chat, text)
    elif state == "confirm":
        await send(ctx, chat, "Please tap one of the options in my last question first 👆")
    elif state == "conditions":
        await send(ctx, chat, "Please tap Done on the conditions message first 👆", cond_kb(ud))
    elif state == "review":
        await send(ctx, chat, "To add another doctor's prescription or run the check, please use these buttons 👇",
                   review_kb(ud))
    else:
        await ask_patient(ctx, chat)


# ---------- button presses ----------
async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d, ud, chat = q.data, ctx.user_data, q.message.chat_id
    state = ud.get("state")

    if d.startswith("p:"):
        kind = d[2:]
        ud.clear()
        if kind == "child":
            ud["state"] = "child_age"
            await safe_edit(q, "Patient: Child")
            await send(ctx, chat, "🧒 How old is the child? Type the age in years, for example: 6\n"
                                  "(For a baby you can type e.g. 8 months.)", Kb([[Btn("⬅️ Back", "change")]]))
            return
        ud["age"], ud["weight"] = (30, 60.0) if kind == "adult" else (70, 60.0)
        ud["label"] = "Adult" if kind == "adult" else "Elderly (65+)"
        await safe_edit(q, f"Patient: {ud['label']}")
        await ask_conditions(ctx, chat)

    elif d in ("t:liver", "t:kidney", "t:done"):
        if state != "conditions":
            return await expired(ctx, chat)
        if d == "t:done":
            picked = [n for n, k in (("liver/alcohol", "risk"), ("kidney disease", "kidney")) if ud.get(k)]
            await safe_edit(q, "Conditions: " + (", ".join(picked) if picked else "none"))
            if picked:
                ud["label"] += " + " + ", ".join(picked)
            ud["rxs"] = []
            await ask_doctor(ctx, chat)
        else:
            key = "risk" if d == "t:liver" else "kidney"
            ud[key] = not ud.get(key, False)
            try:
                await q.edit_message_reply_markup(reply_markup=cond_kb(ud))
            except BadRequest:
                pass

    elif d == "skipdoc":
        if state != "doctor":
            return await expired(ctx, chat)
        await got_doctor(ctx, chat, "")

    elif d == "example":
        if state != "doctor":
            return await expired(ctx, chat)
        await load_example(ctx, chat)

    elif d.startswith("pick:") or d == "skip":
        if state != "confirm" or not ud.get("queue"):
            return await expired(ctx, chat)
        cur = ud["queue"].pop(0)
        if d == "skip":
            await safe_edit(q, f"Skipped '{cur['name']}'. Please check that one manually.")
        else:
            idx = int(d[5:])
            if idx >= len(cur["sugg"]):
                return await expired(ctx, chat)
            brand = cur["sugg"][idx]
            ud["items"].append({"brand": brand, "freq": cur["freq"]})
            await safe_edit(q, f"'{cur['name']}' → {brand}")
        await next_step(ctx, chat)

    elif d == "adddoc":
        if "age" not in ud or "rxs" not in ud:
            return await expired(ctx, chat)
        await ask_doctor(ctx, chat)

    elif d == "checkall":
        if not ud.get("rxs"):
            return await expired(ctx, chat)
        await report(ctx, chat)

    elif d == "undo":
        if not ud.get("rxs"):
            return await expired(ctx, chat)
        gone = ud["rxs"].pop()
        await safe_edit(q, f"Removed the prescription from {gone['doctor']}.")
        if ud["rxs"]:
            await show_review(ctx, chat)
        else:
            await ask_doctor(ctx, chat)

    elif d == "newcheck":
        if "age" not in ud:
            return await expired(ctx, chat)
        ud["rxs"] = []
        await send(ctx, chat, f"🧾 Patient: {ud.get('label', '')}")
        await ask_doctor(ctx, chat)

    elif d == "more":
        await send(ctx, chat, ud.get("rest") or "No more notes.")

    elif d == "change":
        await ask_patient(ctx, chat)

    else:
        await expired(ctx, chat)


async def on_error(update, ctx: ContextTypes.DEFAULT_TYPE):
    logging.error("Error while handling an update: %s", ctx.error, exc_info=ctx.error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await ctx.bot.send_message(update.effective_chat.id,
                                       "⚠️ Something went wrong on my side. Tap /start to try again.")
        except Exception:
            pass


def main():
    app = Application.builder().token(get_token()).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)
    print("Bot running. Leave this window open. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
