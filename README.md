# Traukalender-Monitor (Düsseldorf)

Prüft stündlich die freien **Fr/Sa-Termine im Zeitraum 15.–30.04.2027** in den
Trauorten **Standesamt**, **Standesamt 2** und **Schloss Eller**, rendert daraus eine
**Kachel-Übersicht** (GitHub Pages) und schickt bei **neu freigewordenen Slots** einen
kurzen **Push** (ntfy.sh) mit Link zur Übersicht. Läuft kostenlos in der GitHub-Cloud —
kein eigener Rechner, kein LLM.

## Dateien
- `monitor.py` — holt Tage + Uhrzeiten, erkennt neue Slots, rendert `public/index.html`,
  schreibt `state.json` (Vorzustand) und `status.json` (Push-Entscheidung).
- `.github/workflows/traukalender.yml` — stündlicher Job: ausführen → Pages deployen →
  bei neuen Slots kurzer Push.
- `state.json` — letzter Verfügbarkeitsstand (wird nur bei echter Änderung neu committet).

## Einrichtung (einmalig)

### 1. ntfy (Push)
ntfy-App installieren, ein **geheimes Topic** abonnieren (lang & zufällig), und in GitHub
als Secret hinterlegen: **Settings → Secrets and variables → Actions → New repository secret**,
Name `NTFY_TOPIC`, Wert = der Topic-Name.

### 2. GitHub Pages aktivieren
**Settings → Pages → Build and deployment → Source: „GitHub Actions"**.
Danach erzeugt der Workflow die Übersichtsseite unter
`https://<user>.github.io/<repo>/` — diese URL aufs Handy legen.

### 3. Starten
**Actions → Traukalender-Monitor → Run workflow.** Ab dann läuft es stündlich (:01).

## Verhalten
- Die **Pages-Seite** zeigt immer den aktuellen Stand (alle Orte, Tage, Uhrzeiten);
  neue Slots sind grün mit „NEU" markiert, ein ganz neuer Tag mit „neuer Tag".
- Ein **Push** kommt nur, wenn neue Slots frei werden (oder der Abruf komplett scheitert) —
  kurz, mit Link zur Übersicht. Kein Dauer-Rauschen.

## Anpassen (oben in `monitor.py`)
`TRAUORTE` (Orte/IDs), `WIN_START`/`WIN_END` (Zeitraum), `WEEKDAYS` (Fr=4, Sa=5),
`cron:` in der Workflow-Datei (GitHub-Minimum 5 Min).

Nur lesende Abrufe — es wird nichts reserviert oder gebucht.
