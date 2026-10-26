#!/usr/bin/env python3
"""Traukalender Düsseldorf – holt freie Fr/Sa-Termine, rendert eine Kachel-Ansicht
als HTML und markiert gegenüber dem letzten Lauf neu hinzugekommene Slots.

Zustand wird NICHT in einer lokalen Datei gehalten (jeder geplante Lauf ist eine
frische Session), sondern aus dem zuletzt veröffentlichten Artifact gelesen:
die Session speichert dessen HTML vor dem Lauf nach PREV_HTML; dieses Skript
liest den eingebetteten JSON-Snapshot daraus. Fehlt die Datei oder der Snapshot,
gilt der Lauf als Erstlauf (keine NEU-Markierungen).

Ausgabe:
  - schreibt OUT_HTML (vollständige Kachel-Seite mit eingebettetem Snapshot)
  - druckt eine lesbare Zusammenfassung nach stdout
  - letzte Zeilen (mit '#' beginnend) sind Maschinen-Flags fuer die Session:
      # NEU=<int>        Anzahl neu hinzugekommener Slots
      # FEHLER=<orte>    kommagetrennt, leer wenn keine
      # ERSTLAUF=<0|1>
"""
import subprocess, json, datetime, re, html, os
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Berlin")
except Exception:
    TZ = None  # Fallback: lokale/UTC-Zeit des Runners

# Haupt-Trauorte (fester erster Reiter) — per Name. Alle übrigen, die die
# Startseite liefert, landen automatisch im zweiten Reiter "Weitere Orte".
PRIMARY_NAMES = ["Standesamt", "Standesamt 2", "Schloss Eller"]
# Fallback, falls die Startseite mal nicht lesbar ist:
FALLBACK_TRAUORTE = {
    "Standesamt": 1533, "Standesamt 2": 2906, "Schloss Eller": 1782,
    "Rathaus Benrath": 1576, "Rathaus Eller": 1621, "Schloss Benrath": 1742,
    "Rathaus Ältestenratssaal": 1862, "„Ja in Kürze“ im Standesamt": 39984,
    "TEEKANNE-Belvedere im Kunstpalast": 45283,
}
# Werden in main() aus der Startseite befüllt:
PRIMARY, SECONDARY, TRAUORTE = {}, {}, {}
START_URL = "https://traukalender.duesseldorf.de/de/Traukalender-Landeshauptstadt-Duesseldorf-72.html"
WIN_START = datetime.date(2027, 4, 15)
WIN_END   = datetime.date(2027, 4, 30)
WEEKDAYS  = {4, 5}
WT   = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
WTL  = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
OUT_HTML  = os.environ.get("OUT_HTML", "public/index.html")
SNAP_FILE = os.environ.get("SNAP_FILE", "state.json")      # Vorzustand (commit nur bei Änderung)
STATUS_FILE = os.environ.get("STATUS_FILE", "status.json")  # Push-Entscheidung je Lauf
HOST = "https://traukalender.duesseldorf.de"
DAYS_URL = (HOST + "/common/ajax.php?bereich=portal&modul_id=101"
            "&klasse=tko_buergeransicht&com=ermitteln_termindaten&ortsverwaltung=0"
            "&monat=4&jahr=2027&min=2027-04-15&max=2027-04-30"
            "&sprache=de&texte=traukalender%2Ftexte_buergeransicht")
SLOT_URL = HOST + "/de/buerger_liste_termine_ajax.html"
SLOT_RE  = re.compile(r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}")
SNAP_RE  = re.compile(r'<script id="snapshot" type="application/json">(.*?)</script>', re.S)


def _curl(url):
    out = subprocess.run(
        ["curl", "-s", "-m", "25",
         "-H", "X-Requested-With: XMLHttpRequest",
         "-H", "User-Agent: Mozilla/5.0",
         "-H", "Accept: */*", url],
        capture_output=True, text=True, timeout=40)
    return out.stdout


def fetch_trauorte():
    """Liest die buchbaren Trauorte (Name -> ID) von der Startseite.
    Nur Orte MIT Reservierungslink werden erfasst; geschlossene (ohne Link)
    fehlen automatisch und erscheinen, sobald die Stadt sie reaktiviert.
    Gibt None zurück, wenn die Seite nicht lesbar ist (dann greift der Fallback).
    """
    try:
        page = _curl(START_URL)
        out = {}
        for mm in re.finditer(r"<h2[^>]*>(.*?)</h2>(.*?)(?=<h2|\Z)", page, re.S):
            name = html.unescape(re.sub("<[^>]+>", "", mm.group(1))).strip()
            tid = re.search(r"Start-168\.html\?trauort=(\d+)", mm.group(2))
            if name and tid:
                out[name] = int(tid.group(1))
        return out or None
    except Exception:
        return None


def fetch_days(tid):
    data = json.loads(_curl(f"{DAYS_URL}&trauort={tid}").strip())
    out = []
    for d in data.get("appointments", []):
        dt = datetime.date.fromisoformat(d)
        if WIN_START <= dt <= WIN_END and dt.weekday() in WEEKDAYS:
            out.append(d)
    return sorted(out)


def fetch_slots(tid, tag):
    page = _curl(f"{SLOT_URL}?trauort={tid}&ortsverwaltung=0&tag={tag}")
    slots, seen = [], set()
    for m in SLOT_RE.findall(page):
        s = re.sub(r"\s*-\s*", " – ", m.strip())
        if s not in seen:
            seen.add(s); slots.append(s)
    return slots


def load_prev():
    # Vorzustand aus schlanker state.json (nur echte Verfügbarkeit, kein Zeitstempel).
    try:
        with open(SNAP_FILE, encoding="utf-8") as f:
            st = json.load(f)
        if st and all(isinstance(v, dict) for v in st.values()):
            return st
        return None
    except Exception:
        return None


def save_prev(current):
    with open(SNAP_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=1)


def fmt_short(dstr):
    d = datetime.date.fromisoformat(dstr)
    return f"{WT[d.weekday()]} {d.strftime('%d.%m.%Y')}"

# ----------------------------------------------------------------------------- render

CSS = """
  :root {
    --bg:#f3f0ea; --surface:#fff; --ink:#2a2622; --muted:#7a7267; --line:#e3ddd2;
    --accent:#8a5a3c; --accent-soft:#f0e4da;
    --new:#2f7d4f; --new-soft:#e2f1e7; --new-line:#bfe0cb;
    --demo:#9a6b00; --demo-soft:#f6ecd2;
    --shadow:0 1px 2px rgba(42,38,34,.06),0 6px 18px rgba(42,38,34,.05);
    --font-display:"Fraunces",Georgia,"Times New Roman",serif;
    --font-body:"Inter",system-ui,-apple-system,sans-serif;
  }
  @media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
    --bg:#1c1a17; --surface:#272320; --ink:#ece6dc; --muted:#a89f92; --line:#3a342d;
    --accent:#d7a67f; --accent-soft:#342a22;
    --new:#6fcf97; --new-soft:#22312a; --new-line:#3a5a45;
    --demo:#e0b659; --demo-soft:#332b18;
    --shadow:0 1px 2px rgba(0,0,0,.3),0 6px 18px rgba(0,0,0,.3); color-scheme:dark;}}
  :root[data-theme="dark"]{
    --bg:#1c1a17; --surface:#272320; --ink:#ece6dc; --muted:#a89f92; --line:#3a342d;
    --accent:#d7a67f; --accent-soft:#342a22;
    --new:#6fcf97; --new-soft:#22312a; --new-line:#3a5a45;
    --demo:#e0b659; --demo-soft:#332b18;
    --shadow:0 1px 2px rgba(0,0,0,.3),0 6px 18px rgba(0,0,0,.3); color-scheme:dark;}
  *{box-sizing:border-box;}
  body{background:var(--bg);color:var(--ink);font-family:var(--font-body);line-height:1.5;-webkit-font-smoothing:antialiased;}
  .wrap{max-width:960px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:32px 48px;}
  header.top{margin-bottom:20px;}
  .eyebrow{font-size:.74rem;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:600;margin:0 0 8px;}
  h1{font-family:var(--font-display);font-weight:600;font-size:clamp(1.8rem,5vw,2.6rem);line-height:1.1;margin:0 0 10px;text-wrap:balance;}
  .window{font-size:1rem;color:var(--muted);margin:0;}
  .stand{display:inline-flex;align-items:center;gap:7px;margin-top:14px;font-size:.82rem;color:var(--muted);background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:5px 13px;}
  .dot{width:7px;height:7px;border-radius:50%;background:var(--new);}
  .change-note{display:flex;align-items:center;gap:9px;margin:18px 0 4px;font-size:.92rem;font-weight:600;color:var(--new);background:var(--new-soft);border:1px solid var(--new-line);border-radius:12px;padding:11px 15px;}
  .change-note.flat{color:var(--muted);background:var(--surface);border-color:var(--line);font-weight:500;}
  .tabs{margin-top:16px;}
  .tabin{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none;}
  .tablbl{display:inline-flex;align-items:center;gap:7px;cursor:pointer;font-family:var(--font-display);font-size:1.05rem;font-weight:600;color:var(--muted);padding:6px 2px 10px;margin-right:24px;border-bottom:2px solid transparent;transition:color .15s;}
  .tablbl:hover{color:var(--ink);}
  .tabnew{font-family:var(--font-body);font-size:.66rem;font-weight:800;letter-spacing:.04em;background:var(--new);color:#fff;border-radius:999px;padding:1px 7px;}
  :root[data-theme="dark"] .tabnew,:root:not([data-theme="light"]) .tabnew{color:#16231b;}
  .tabline{border-bottom:1px solid var(--line);margin-top:-1px;}
  .panel{display:none;}
  #tab-1:checked ~ .panel-1{display:block;}
  #tab-2:checked ~ .panel-2{display:block;}
  #tab-1:checked ~ .tablbl[for="tab-1"],#tab-2:checked ~ .tablbl[for="tab-2"]{color:var(--ink);border-bottom-color:var(--accent);}
  .panel section.loc:first-child{margin-top:22px;}
  section.loc{margin-top:30px;}
  .loc-head{display:flex;align-items:baseline;gap:10px;margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid var(--line);}
  .loc-head h2{font-family:var(--font-display);font-size:1.3rem;font-weight:600;margin:0;}
  .loc-count{font-size:.8rem;color:var(--muted);font-variant-numeric:tabular-nums;}
  .days{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px;}
  .day{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:15px 16px 16px;box-shadow:var(--shadow);min-width:0;position:relative;}
  .day.has-new{border-color:var(--new-line);box-shadow:var(--shadow),0 0 0 2px var(--new-soft);}
  .day-top{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:12px;}
  .wday{font-size:.72rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);}
  .date{font-family:var(--font-display);font-size:1.05rem;font-weight:600;font-variant-numeric:tabular-nums;}
  .nslots{font-size:.72rem;color:var(--muted);background:var(--accent-soft);border-radius:999px;padding:2px 9px;font-variant-numeric:tabular-nums;white-space:nowrap;}
  .nslots.new{color:var(--new);background:var(--new-soft);}
  .slots{display:flex;flex-wrap:wrap;gap:7px;}
  .slot{font-size:.82rem;font-variant-numeric:tabular-nums;background:var(--accent-soft);color:var(--accent);border:1px solid transparent;border-radius:8px;padding:5px 9px;white-space:nowrap;font-weight:500;}
  .slot.single{background:transparent;border-color:var(--accent);}
  .slot.new{background:var(--new-soft);color:var(--new);border-color:var(--new-line);display:inline-flex;align-items:center;gap:6px;font-weight:600;}
  .slot.new::after{content:"NEU";font-size:.6rem;letter-spacing:.08em;font-weight:800;background:var(--new);color:#fff;border-radius:4px;padding:1px 4px;}
  :root[data-theme="dark"] .slot.new::after,:root:not([data-theme="light"]) .slot.new::after{color:#16231b;}
  .empty{color:var(--muted);font-size:.9rem;font-style:italic;margin:4px 0 0;}
  footer{margin-top:40px;padding-top:16px;border-top:1px solid var(--line);font-size:.78rem;color:var(--muted);}
  footer a{color:var(--accent);}
"""

FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Fraunces:opsz,wght@9..144,500;9..144,600&'
         'family=Inter:wght@400;500;600;700;800&display=swap">')


def esc(s):
    return html.escape(str(s))


def render(current, prev, first_run, errors, now):
    parts = []
    parts.append("<title>Traukalender Düsseldorf</title>")
    parts.append('<meta name="claude:viewport-fit-sides" content="cover">')
    parts.append("<style>" + CSS + "</style>")
    parts.append(FONTS)
    parts.append('<div class="wrap">')
    parts.append('<header class="top">')
    parts.append('<p class="eyebrow">Eheschließungstermine · Düsseldorf</p>')
    parts.append("<h1>Traukalender</h1>")
    parts.append('<p class="window">Freitags &amp; samstags · 15.–30. April 2027</p>')
    parts.append(f'<span class="stand"><span class="dot"></span> Stand: {esc(now)} Uhr</span>')
    parts.append("</header>")

    total_new = sum(
        1
        for loc in current for tag in current[loc] for s in current[loc][tag]
        if (not first_run) and s not in set(prev.get(loc, {}).get(tag, []))
    )

    if first_run:
        parts.append('<div class="change-note flat">Erster Lauf — Ausgangsstand erfasst, daher keine Neu-Markierungen.</div>')
    elif total_new:
        wort = "neuer Termin" if total_new == 1 else "neue Termine"
        parts.append(f'<div class="change-note">{total_new} {wort} seit letztem Lauf</div>')
    else:
        parts.append('<div class="change-note flat">Keine Änderung seit letztem Lauf.</div>')

    def section_html(loc):
        cur = current.get(loc, {})
        oldloc = prev.get(loc, {})
        n_slots = sum(len(v) for v in cur.values())
        n_days = len(cur)
        p = ['<section class="loc">', '<div class="loc-head">', f"<h2>{esc(loc)}</h2>"]
        if loc in errors:
            p.append('<span class="loc-count">Abruf fehlgeschlagen – letzter Stand</span>')
        else:
            sl = "Slot" if n_slots == 1 else "Slots"
            tg = "Tag" if n_days == 1 else "Tage"
            p.append(f'<span class="loc-count">{n_slots} {sl} · {n_days} {tg}</span>')
        p.append("</div>")
        if not cur:
            p.append('<p class="empty">Keine freien Fr/Sa-Termine.</p>')
            p.append("</section>")
            return "\n".join(p)
        p.append('<div class="days">')
        for tag in sorted(cur):
            slots = cur[tag]
            oldslots = set(oldloc.get(tag, []))
            new_day = (not first_run) and (tag not in oldloc)
            new_here = [s for s in slots if (not first_run) and s not in oldslots]
            has_new = bool(new_here)
            d = datetime.date.fromisoformat(tag)
            p.append(f'<div class="day{" has-new" if has_new else ""}">')
            p.append('<div class="day-top">')
            p.append(f'<div><div class="wday">{WTL[d.weekday()]}</div>'
                     f'<div class="date">{d.strftime("%d.%m.%Y")}</div></div>')
            if new_day:
                p.append('<span class="nslots new">neuer Tag</span>')
            elif has_new:
                p.append(f'<span class="nslots new">+{len(new_here)} neu</span>')
            else:
                p.append(f'<span class="nslots">{len(slots)} frei</span>')
            p.append("</div>")
            p.append('<div class="slots">')
            for s in slots:
                is_new = (not first_run) and s not in oldslots
                p.append(f'<span class="{"slot new" if is_new else "slot"}">{esc(s)}</span>')
            p.append("</div>")
            p.append("</div>")
        p.append("</div>")
        p.append("</section>")
        return "\n".join(p)

    def group_new(group):
        return sum(1 for loc in group for tag in current.get(loc, {})
                   for s in current[loc][tag]
                   if (not first_run) and s not in set(prev.get(loc, {}).get(tag, [])))

    def tab_badge(n):
        return f' <span class="tabnew">{n} neu</span>' if n else ""

    parts.append('<div class="tabs">')
    parts.append('<input type="radio" name="tab" id="tab-1" class="tabin" checked>')
    parts.append(f'<label for="tab-1" class="tablbl">Hauptorte{tab_badge(group_new(PRIMARY))}</label>')
    parts.append('<input type="radio" name="tab" id="tab-2" class="tabin">')
    parts.append(f'<label for="tab-2" class="tablbl">Weitere Orte{tab_badge(group_new(SECONDARY))}</label>')
    parts.append('<div class="tabline"></div>')
    parts.append('<div class="panel panel-1">')
    for loc in PRIMARY:
        parts.append(section_html(loc))
    parts.append("</div>")
    parts.append('<div class="panel panel-2">')
    for loc in SECONDARY:
        parts.append(section_html(loc))
    parts.append("</div>")
    parts.append("</div>")

    foot = ("Automatischer Monitor – nur lesender Abruf, keine Reservierung. "
            "Neu hinzugekommene Slots erscheinen grün mit „NEU\"-Markierung, ein ganz "
            "neuer Tag mit dem Hinweis „neuer Tag\". Quelle: "
            '<a href="https://traukalender.duesseldorf.de" target="_blank" rel="noopener">'
            "traukalender.duesseldorf.de</a>.")
    if errors:
        foot += " Abruf-Probleme bei: " + esc(", ".join(errors)) + " (alter Stand beibehalten)."
    parts.append(f"<footer>{foot}</footer>")
    parts.append("</div>")
    snap = json.dumps(current, ensure_ascii=False)
    parts.append(f'<script id="snapshot" type="application/json">{snap}</script>')
    return "\n".join(parts), total_new


def main():
    global PRIMARY, SECONDARY, TRAUORTE
    allt = fetch_trauorte() or dict(FALLBACK_TRAUORTE)
    PRIMARY = {n: allt[n] for n in PRIMARY_NAMES if n in allt}
    SECONDARY = {n: i for n, i in allt.items() if n not in PRIMARY}
    TRAUORTE = {**PRIMARY, **SECONDARY}

    prev = load_prev()
    first_run = prev is None
    prev = prev or {}
    now = datetime.datetime.now(TZ).strftime("%d.%m.%Y, %H:%M")
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

    html_out, total_new = render(current, prev, first_run, errors, now)
    d = os.path.dirname(OUT_HTML)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_out)
    # Vorzustand fortschreiben (nur erfolgreich geholte Orte überschreiben)
    new_snap = dict(prev)
    for loc in TRAUORTE:
        if loc not in errors:
            new_snap[loc] = current[loc]
    save_prev(new_snap)

    # lesbare Zusammenfassung (auch als Benachrichtigungstext nutzbar)
    lines = [f"\U0001F5D3 Traukalender Düsseldorf — Fr/Sa 15.–30.04.2027 (Stand: {now})", ""]
    for loc in TRAUORTE:
        lines.append(loc)
        cur = current.get(loc, {})
        oldloc = prev.get(loc, {})
        if not cur:
            lines.append("  – keine freien Fr/Sa-Termine")
        for tag in sorted(cur):
            lines.append(f"  – {fmt_short(tag)}")
            oldslots = set(oldloc.get(tag, []))
            if not cur[tag]:
                lines.append("    –– (Termine vorhanden, Uhrzeit nicht auslesbar)")
            for s in cur[tag]:
                mark = "  (NEU)" if (not first_run) and s not in oldslots else ""
                lines.append(f"    –– {s}{mark}")
        lines.append("")
    if first_run:
        lines.append("ℹ Erster Lauf — Ausgangsstand erfasst, daher keine (NEU)-Markierungen.")
    elif not total_new:
        lines.append("— keine Änderung seit letztem Lauf —")
    else:
        wort = "neuer Slot" if total_new == 1 else "neue Slots"
        lines.append(f"✅ {total_new} {wort} seit letztem Lauf (siehe (NEU)).")
    if errors:
        lines.append("⚠ Abruf-Probleme bei: " + ", ".join(errors) + " (alter Stand beibehalten)")
    print("\n".join(lines).rstrip())
    print(f"# NEU={total_new}")
    print(f"# FEHLER={','.join(errors)}")
    print(f"# ERSTLAUF={1 if first_run else 0}")

    # Kurz-Status für den Workflow — es wird IMMER gepusht (auch "keine Änderung").
    errors_all = len(errors) == len(TRAUORTE)
    total_free = sum(len(v) for loc in current for v in current[loc].values())
    hhmm = now.split(", ")[-1]
    if total_new:
        wort = "neuer Slot" if total_new == 1 else "neue Slots"
        headline = f"\U0001F514 {total_new} {wort} im Traukalender (Fr/Sa 15.–30.04.2027)"
        priority, tags = "high", "bell,tada"
    elif errors_all:
        headline = f"⚠ Abruf aktuell nicht möglich ({hhmm})"
        priority, tags = "default", "warning"
    elif first_run:
        headline = f"Überwachung gestartet — {total_free} freie Slots erfasst ({hhmm})"
        priority, tags = "low", "calendar"
    else:
        headline = f"Keine Änderung — {total_free} freie Slots (Stand {hhmm})"
        priority, tags = "low", "calendar"
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump({"new": total_new, "errors": errors, "errors_all": errors_all,
                   "first_run": first_run, "headline": headline,
                   "priority": priority, "tags": tags, "stand": now},
                  f, ensure_ascii=False)


if __name__ == "__main__":
    main()
