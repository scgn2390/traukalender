#!/usr/bin/env python3
"""Verfügbarkeits-Monitor Traukalender Düsseldorf — ohne LLM, für GitHub Actions.

Ruft headless die freien Fr/Sa-Termine (15.-30.04.2027) der ausgewählten Trauorte
ab, vergleicht mit dem letzten Lauf (state.json) und schickt das Ergebnis per
ntfy.sh als Push aufs Handy. Neue Zeitslots werden mit "(NEU)" markiert.

Konfiguration über Umgebungsvariablen:
  NTFY_TOPIC   (Pflicht) geheimes ntfy-Topic, z.B. "traukalender-x7k2p9q"
  NTFY_SERVER  (optional) Standard https://ntfy.sh
  ONLY_ON_CHANGE=1  (optional) nur pushen, wenn sich etwas geändert hat
  DRY_RUN=1    (optional) nichts senden, nur ausgeben (zum Testen)
"""
import subprocess, json, datetime, re, os, sys

TRAUORTE = {"Standesamt": 1533, "Standesamt 2": 2906, "Schloss Eller": 1782}
WIN_START = datetime.date(2027, 4, 15)
WIN_END   = datetime.date(2027, 4, 30)
WEEKDAYS  = {4, 5}  # Fr=4, Sa=5
WT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
HOST = "https://traukalender.duesseldorf.de"
DAYS_URL = (HOST + "/common/ajax.php?bereich=portal&modul_id=101"
            "&klasse=tko_buergeransicht&com=ermitteln_termindaten&ortsverwaltung=0"
            "&monat=4&jahr=2027&min=2027-04-15&max=2027-04-30"
            "&sprache=de&texte=traukalender%2Ftexte_buergeransicht")
SLOT_URL = HOST + "/de/buerger_liste_termine_ajax.html"
SLOT_RE = re.compile(r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}")


def _curl(url):
    out = subprocess.run(
        ["curl", "-s", "-m", "25",
         "-H", "X-Requested-With: XMLHttpRequest",
         "-H", "User-Agent: Mozilla/5.0",
         "-H", "Accept: */*", url],
        capture_output=True, text=True, timeout=40)
    return out.stdout


def fetch_days(tid):
    data = json.loads(_curl(f"{DAYS_URL}&trauort={tid}").strip())
    out = []
    for d in data.get("appointments", []):
        dt = datetime.date.fromisoformat(d)
        if WIN_START <= dt <= WIN_END and dt.weekday() in WEEKDAYS:
            out.append(d)
    return sorted(out)


def fetch_slots(tid, tag):
    html = _curl(f"{SLOT_URL}?trauort={tid}&ortsverwaltung=0&tag={tag}")
    slots, seen = [], set()
    for m in SLOT_RE.findall(html):
        s = re.sub(r"\s*-\s*", " - ", m.strip())
        if s not in seen:
            seen.add(s); slots.append(s)
    return slots


def fmt_day(dstr):
    d = datetime.date.fromisoformat(dstr)
    return f"{WT[d.weekday()]} {d.strftime('%d.%m.%Y')}"


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            st = json.load(f)
        if st and all(isinstance(v, dict) for v in st.values()):
            return st
        return None
    except Exception:
        return None


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def notify(title, body, priority, tags):
    topic = os.environ.get("NTFY_TOPIC")
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    if not topic or os.environ.get("DRY_RUN"):
        print(f"[DRY_RUN] Title={title} Priority={priority} Tags={tags}\n{body}")
        return
    subprocess.run(
        ["curl", "-s", "-m", "20",
         "-H", f"Title: {title}",
         "-H", f"Priority: {priority}",
         "-H", f"Tags: {tags}",
         "--data-binary", body.encode("utf-8"),
         f"{server}/{topic}"],
        timeout=30)


def main():
    prev = load_state()
    first_run = prev is None
    prev = prev or {}
    now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")

    current, errors = {}, []
    for loc, tid in TRAUORTE.items():
        try:
            days = fetch_days(tid)
        except Exception:
            errors.append(loc)
            current[loc] = prev.get(loc, {})
            continue
        daymap = {}
        for tag in days:
            try:
                daymap[tag] = fetch_slots(tid, tag)
            except Exception:
                daymap[tag] = prev.get(loc, {}).get(tag, [])
        current[loc] = daymap

    lines = [f"\U0001F5D3 Traukalender Düsseldorf — Fr/Sa 15.–30.04.2027 (Stand: {now})", ""]
    any_new = False
    changed = (current != prev)
    for loc in TRAUORTE:
        lines.append(loc)
        cur = current.get(loc, {})
        oldloc = prev.get(loc, {})
        if not cur:
            lines.append("  – keine freien Fr/Sa-Termine")
        for tag in sorted(cur):
            lines.append(f"  – {fmt_day(tag)}")
            oldslots = set(oldloc.get(tag, []))
            if not cur[tag]:
                lines.append("    –– (Termine vorhanden, Uhrzeit nicht auslesbar)")
            for s in cur[tag]:
                is_new = (not first_run) and (s not in oldslots)
                if is_new:
                    any_new = True
                lines.append(f"    –– {s}" + ("  (NEU)" if is_new else ""))
        lines.append("")

    if first_run:
        lines.append("ℹ Erster Lauf — Ausgangsstand erfasst, daher keine (NEU)-Markierungen.")
    elif not any_new:
        lines.append("— keine Änderung seit letztem Lauf —")
    if errors:
        lines.append("⚠ Abruf-Probleme bei: " + ", ".join(errors) + " (alter Stand beibehalten)")

    # State nur mit erfolgreich geholten Locations fortschreiben
    new_state = dict(prev)
    for loc in TRAUORTE:
        if loc not in errors:
            new_state[loc] = current[loc]
    save_state(new_state)

    body = "\n".join(lines).rstrip()

    # Nur bei Änderung pushen, falls so konfiguriert (Erstlauf immer)
    if os.environ.get("ONLY_ON_CHANGE") and not changed and not first_run:
        print("ONLY_ON_CHANGE: keine Änderung, kein Push.")
        print(body)
        return

    if any_new:
        title, priority, tags = "NEUE Termine! Traukalender Fr/Sa 15.-30.04.", "high", "bell,tada"
    elif errors:
        title, priority, tags = "Traukalender-Monitor (Abruf-Problem)", "default", "warning"
    else:
        title, priority, tags = "Traukalender Fr/Sa 15.-30.04.", "low", "calendar"

    notify(title, body, priority, tags)
    print(body)


if __name__ == "__main__":
    main()
